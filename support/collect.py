"""공개 기관 공고 수집. 추출 결과는 신청 가능 판정이 아니며 실패를 빈 결과로 덮지 않는다.

state.json: 재시도/역수집/공고 및 첨부 변경 이력. feed.json: 공개시각을 가진 일별 게시본.
웹페이지/첨부는 신뢰하지 않는 데이터이며 스크립트·매크로·지시를 실행하지 않는다.
"""
from __future__ import annotations
import argparse, concurrent.futures, datetime as dt, hashlib, io, ipaddress, json, os
import pathlib, re, shutil, socket, struct, sys, threading, time, urllib.parse as up
import urllib.robotparser, zipfile, zlib, xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader
import olefile

KST = dt.timezone(dt.timedelta(hours=9))
HERE = pathlib.Path(__file__).resolve().parent
AGENT = 'UnionOneSupportBot/1.0 (+https://github.com/unionone-universe/work-board)'
CATEGORIES = {
 '부동산·건설': r'부동산|철거|인테리어|건설|건축|리모델링|도시재생|빈집|스마트도시|공간정보|프롭테크',
 '앱·플랫폼': r'소프트웨어|플랫폼|디지털|정보통신|스마트|데이터|인공지능|ICT|AI\b|앱\b|SW\b|IT\b|기술창업|온라인|전자상거래',
 '법인·경영': r'경영|법인|중소기업|소상공인|창업|기업|고용|자금|융자|보증|컨설팅|세무|판로|수출',
 '문화·예술': r'예술|문화|무용|공연|콘텐츠|안무|창작|아트|매니지먼트',
}
FIELDS = {
 'audience':r'신청\s*자격|지원\s*대상|신청\s*대상|모집\s*대상|참여\s*대상|☞',
 'benefit':r'지원\s*내용|지원\s*규모|지원\s*금액|지원\s*한도|융자\s*한도|보증\s*한도|☞',
 'exclusions':r'지원\s*제외|신청\s*제외|제외\s*대상|신청\s*제한|참여\s*제한|체납|중복\s*지원',
 'copay':r'자부담|자기부담|기업부담|민간부담|본인부담|부담금|보증료|금리|이자율',
 'period':r'신청\s*기간|접수\s*기간|신청\s*기한|접수\s*기한|모집\s*기간|공모\s*기간|접수\s*일정|마감\s*일|신청기간',
}

def now(): return dt.datetime.now(KST)
def stamp(): return now().isoformat(timespec='seconds')
def digest(x): return hashlib.sha256(x if isinstance(x, bytes) else x.encode('utf-8')).hexdigest()
def tidy(t): return re.sub(r'[ \t\xa0]+',' ',str(t)).strip()
def flat(t): return re.sub(r'\s+',' ',str(t)).strip()
def date_iso(y,m,d):
 try: return dt.date(int(y),int(m),int(d)).isoformat()
 except (ValueError,TypeError): return ''
def valid_dates(t):
 return [d for y,m,day in re.findall(r'(?<!\d)(20\d{2})[.\-/년]\s*(\d{1,2})[.\-/월]\s*(\d{1,2})',t) if (d:=date_iso(y,m,day))]
def schedule(period,title=''):
 """Only labeled date ranges or an explicit ~ deadline; a bare event date is not a deadline."""
 parts=re.split(r'[~∼～]',period,maxsplit=1)
 dates=valid_dates(parts[0]);start=dates[-1] if dates else '';end='';at=''
 # A programme's title year may differ from the application year. Never infer from the title.
 yr=re.search(r'20\d{2}',parts[0])
 m=re.match(r'\s*(?:(20\d{2})[.\-/년]\s*)?(\d{1,2})[.\-/월]\s*(\d{1,2})([\s\S]{0,35})',parts[1]) if len(parts)>1 else None
 if m and (m[1] or yr):
  y=int(m[1] or yr[0]);end=date_iso(y,m[2],m[3])
  if end and start and end<start and not m[1] and int(m[2])<int(start[5:7]):end=date_iso(y+1,m[2],m[3])
  clock=re.search(r'(\d{1,2})\s*[:시]\s*(\d{2})?',m[4])
  if end and clock and int(clock[1])<24 and int(clock[2] or 0)<60:at=end+f'T{int(clock[1]):02d}:{int(clock[2] or 0):02d}:00+09:00'
 return start,end,at
def safe_url(url, base=''):
 u=up.urlsplit(up.urljoin(base,url.strip()))
 if u.scheme not in ('http','https') or not u.hostname or u.username or u.password or u.port not in (None,80,443):
  raise ValueError('공개 웹 주소가 아님')
 try:
  for a in socket.getaddrinfo(u.hostname,None):
   if not ipaddress.ip_address(a[4][0]).is_global: raise ValueError('내부 주소 차단')
 except socket.gaierror as e: raise ValueError('기관 주소 확인 실패') from e
 return up.urlunsplit((u.scheme,u.netloc,u.path,u.query,''))

class Web:
 def __init__(self, seconds=1800):
  current=now()
  if current.hour<8:
   seconds=min(seconds,max(1,(current.replace(hour=8,minute=0,second=0,microsecond=0)-current).total_seconds()-45))
  self.end=time.monotonic()+seconds;self.locks={};self.guard=threading.Lock();self.robots={};self.local=threading.local()
 def expired(self): return time.monotonic()>self.end
 def get(self,url,limit=24*1024*1024,robots=True):
  if self.expired(): raise TimeoutError('조사 실행 시간 종료 — 다음 실행에서 계속')
  if not hasattr(self.local,'session'):self.local.session=requests.Session()
  for redirect in range(6):
   url=safe_url(url);host=up.urlsplit(url).netloc
   with self.guard: lock=self.locks.setdefault(host,threading.RLock())
   with lock:
    if robots:
     root=up.urlunsplit((*up.urlsplit(url)[:2],'/robots.txt','',''))
     if root not in self.robots:
      try:
       b,_,_=self.get(root,256000,False);rp=urllib.robotparser.RobotFileParser();rp.parse(b.decode('utf8',errors='replace').splitlines());self.robots[root]=rp
      except Exception: self.robots[root]=None
     rp=self.robots[root]
     if rp and not rp.can_fetch(AGENT,url): raise ValueError('기관 robots 규칙으로 자동 열람 제한')
    time.sleep(.2)
    for attempt in range(3):
     try:
      with self.local.session.get(url,headers={'User-Agent':AGENT},timeout=(8,30),stream=True,allow_redirects=False) as r:
       if r.is_redirect:
        url=up.urljoin(url,r.headers.get('Location',''));break
       if r.status_code in (429,500,502,503,504) and attempt<2:
        time.sleep(2**attempt);continue
       r.raise_for_status();data=bytearray()
       for chunk in r.iter_content(65536):
        data.extend(chunk)
        if len(data)>limit:raise ValueError('파일 크기 제한 초과 — 원문 확인 필요')
       return bytes(data),dict(r.headers),url
     except (requests.Timeout,requests.ConnectionError):
      if attempt==2:raise
      time.sleep(2**attempt)
    else:raise ValueError('기관 응답 실패')
  raise ValueError('지나친 주소 이동')

def soup_of(data):
 for enc in ('utf-8-sig','cp949'):
  try:return BeautifulSoup(data.decode(enc),'html.parser')
  except UnicodeDecodeError:pass
 return BeautifulSoup(data,'html.parser')

def text_of(node):
 clone=BeautifulSoup(str(node),'html.parser')
 for e in clone.select('script,style,nav,footer,header,form input,button,.boardPN,.boardBottom'):e.decompose()
 # Inline formatting must not split Korean words; block boundaries still delimit facts.
 for e in clone.find_all(['p','li','tr','div','dt','dd','h1','h2','h3','h4','br']):e.append('\n')
 return '\n'.join(tidy(x) for x in clone.get_text(' ').splitlines() if tidy(x))

def list_links(src, soup, base):
 result={};kind=src['kind']
 for a in soup.select('a,button'):
  h=a.get('href','');js=h+' '+a.get('onclick','');title=flat(a.get_text(' ',strip=True));u=''
  if kind=='bizinfo' and 'selectSIIA200Detail' in h:
   q=up.parse_qs(up.urlsplit(h).query);pid=q.get('pblancId',[''])[0]
   if pid:u='https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId='+pid
  elif kind=='kstartup' and (m:=re.search(r'go_view\((\d+)\)',js)):
   u='https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do?schM=view&pbancSn='+m[1]
   t=a.select_one('.tit,.title,.biz_tit');title=flat(t.get_text(' ',strip=True)) if t else title
  elif kind=='gokams' and 'introduction_view.aspx' in h:
   u=up.urljoin(base,'introduction_view.aspx?Idx='+up.parse_qs(up.urlsplit(h).query)['Idx'][0])
  elif kind=='dgfca' and (m:=re.search(r'goDetail\((\d+)\)',js)):
   u='https://www.dgfca.or.kr/article/NOTICE/detail/'+m[1]
   t=a.select_one('.title,.tit,.subject');title=flat(t.get_text(' ',strip=True)) if t else title
  elif kind=='arko' and ('/board/view/4013?' in h or 'artnuri.or.kr/crawler/info/view.do?' in h):
   u=up.urljoin(base,h);q=up.parse_qs(up.urlsplit(u).query)
   keys=['bid','cid'] if 'cid' in q else list(q)
   u=up.urlunsplit((*up.urlsplit(u)[:3],up.urlencode({k:q[k][0] for k in keys if k in q}),''))
   t=a.select_one('h3,h4,.title,.tit,strong');title=flat(t.get_text(' ',strip=True)) if t else title
  elif kind=='dpis' and a.get('data-id','').startswith('NOTICE_'):
   u='https://dpis.or.kr/page/businessDetail.do?menuId=101000000&noticeId='+a['data-id']
   title=a.get('title',title).removesuffix(' 자세히 보기')
  elif kind=='dash' and (m:=re.search(r"fn_project_detail\('(PROJECT_\d+)'\)",js)):
   u='https://startup.daegu.go.kr/index.do?menu_id=00002552&menu_link='+up.quote('/front/project/projectFrontDetail.do?project_id='+m[1],safe='')
   t=a.select_one('.tit');title=flat(t.get_text(' ',strip=True)) if t else title
  elif kind=='dip' and (m:=re.search(r"read\('[^']*','(\d+)'\)",js)):
   u=up.urljoin(base,'boardRead.ubs?fboardcd=business&fboardnum='+m[1])
  if u and len(title)>6 and title!='자세히 보기':result[u]={'url':u,'title':title,'sourceId':src['id']}
 return list(result.values())

def snippets(text,pattern,max_chars=650):
 lines=[flat(x) for x in text.splitlines() if flat(x)];hits=[]
 for i,line in enumerate(lines):
  if re.search(pattern,line,re.I):
   # If a heading stands alone include the next paragraph; never synthesize eligibility.
   v=line+(' '+lines[i+1] if len(line)<28 and i+1<len(lines) else '')
   if v not in hits:hits.append(v)
 result='\n'.join(hits)
 return result if len(result)<=max_chars else result[:max_chars]+'… (발췌 · 나머지 조건은 원문 확인)'

def extract_binary(data,name,ocr=True,depth=0):
 """Return text plus explicit unresolved parts; don't execute documents or macros."""
 issues=[];texts=[]
 if data.startswith(b'%PDF'):
  pdf=PdfReader(io.BytesIO(data))
  if pdf.is_encrypted and not pdf.decrypt(''):return '',['암호화 PDF']
  if len(pdf.pages)>200:return '',['PDF 200쪽 초과 — 원문 확인 필요']
  for i,p in enumerate(pdf.pages):
   t=p.extract_text() or ''
   if len(re.sub(r'\s','',t))<30:
    if ocr and shutil.which('tesseract'):
     try:
      import pypdfium2 as pdfium, pytesseract
      doc=pdfium.PdfDocument(data);page=doc[i];bmp=page.render(scale=2)
      t=pytesseract.image_to_string(bmp.to_pil(),lang='kor+eng',timeout=45)
      bmp.close();page.close();doc.close()
     except Exception:t=''
    if len(re.sub(r'\s','',t))<20:issues.append(f'PDF {i+1}쪽 문자 확인 불가')
   texts.append(t)
 elif olefile.isOleFile(io.BytesIO(data)):
  with olefile.OleFileIO(io.BytesIO(data)) as hwp:
   if not hwp.exists('FileHeader'):return '',['HWP 외 OLE 문서']
   header=hwp.openstream('FileHeader').read();flags=struct.unpack_from('<I',header,36)[0]
   if flags & 6:return '',['암호화/배포용 HWP']
   for path in sorted(hwp.listdir()):
    if len(path)==2 and path[0]=='BodyText' and path[1].startswith('Section'):
     chunk=hwp.openstream(path).read()
     if flags&1:
      de=zlib.decompressobj(-15);chunk=de.decompress(chunk,32*1024*1024)
      if de.unconsumed_tail:return '',['HWP 압축 해제 크기 제한']
     pos=0
     while pos+4<=len(chunk):
      rec=struct.unpack_from('<I',chunk,pos)[0];pos+=4;size=rec>>20
      if size==4095:
       if pos+4>len(chunk):break
       size=struct.unpack_from('<I',chunk,pos)[0];pos+=4
      if pos+size>len(chunk):issues.append('HWP 손상된 문단');break
      if rec&1023==67:texts.append(chunk[pos:pos+size].decode('utf-16le',errors='replace'))
      pos+=size
 elif zipfile.is_zipfile(io.BytesIO(data)):
  if depth>1:return '',['중첩 압축파일 — 원문 확인 필요']
  with zipfile.ZipFile(io.BytesIO(data)) as z:
   infos=z.infolist()
   if sum(i.file_size for i in infos)>64*1024*1024 or len(infos)>400:return '',['압축 해제 크기 제한']
   is_hwpx=any(re.fullmatch(r'Contents/section\d+\.xml',i.filename) for i in infos)
   for f in infos:
    if f.is_dir():continue
    if is_hwpx:
     if re.fullmatch(r'Contents/section\d+\.xml',f.filename):
      root=ET.fromstring(z.read(f));texts.extend(''.join(x.itertext()) for x in root.iter() if x.tag.endswith('}p'))
    elif re.search(r'\.(pdf|hwp|hwpx|zip)$',f.filename,re.I):
     t,w=extract_binary(z.read(f),f.filename,ocr,depth+1);texts.append(t);issues.extend(f.filename+': '+x for x in w)
    else:issues.append(f.filename+': 읽지 못한 형식')
 elif re.search(r'\.(png|jpe?g|tiff?)$',name,re.I) and ocr and shutil.which('tesseract'):
  import pytesseract
  from PIL import Image
  texts.append(pytesseract.image_to_string(Image.open(io.BytesIO(data)),lang='kor+eng',timeout=45))
 else:issues.append('읽지 못한 형식 — 원문 확인 필요')
 text='\n'.join(texts);text=re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]',' ',text)
 if not text.strip() and not issues:issues.append('문자 추출 결과 없음')
 return text,issues

def attachments(node,base):
 found={}
 for a in node.select('a[href]'):
  h=a['href'];label=a.get('title') or flat(a.get_text(' ',strip=True)) or up.unquote(h.rsplit('/',1)[-1])
  js=h+' '+a.get('onclick','')
  if (m:=re.search(r"fn_gloDownFile\('([^']+)',\s*'([^']+)'\)",js)):
   h='/cmm/fileDown.do?fileId='+up.quote(m[1])+'&fileSn='+up.quote(m[2])
  if (m:=re.search(r"fn_egov_downFile\('([^']+)',\s*'([^']+)'\)",js)):
   code=node.select_one('[id="encodeFileId'+m[1]+'"]')
   if code:h='/icms/cmm/fms/FileDownForBoard.do?'+up.urlencode({'atchFileId':m[1],'fileSn':m[2],'encodeFileId':code.get('value','')})
  if re.search(r'\.(pdf|hwp|hwpx|zip|xlsx?|docx?|png|jpg)(?:$|\?)|fileDown|filedown|download|atchFile',h,re.I):
   if h.startswith(('javascript:','#')):continue
   u=up.urljoin(base,h);found[u]={'url':u,'name':label}
 return list(found.values())

def detail(web,src,entry,old):
 data,_,url=web.get(entry['url']);s=soup_of(data)
 candidates=s.select(src['body']);body=max(candidates,key=lambda x:len(x.get_text()),default=None)
 if not body:raise ValueError('공고 본문 영역을 찾지 못함')
 bodycopy=BeautifulSoup(str(body),'html.parser')
 for e in bodycopy.select('.viewInfo,.viewNav,.bbsView_info,.boardPN,.snsTop,.snsBottom,.sns_wrap'):e.decompose()
 for e in bodycopy.find_all(['li','tr']):
  if re.search(r'조회\s*수',e.get_text()) and len(e.get_text())<100:e.decompose()
 for e in bodycopy.select('.board-read-table__column3--item'):
  if '조회수' in e.get_text():e.decompose()
 if src['kind']=='gokams':
  meta=bodycopy.select_one('.boardViewT tbody tr')
  if meta:meta.decompose()
 text=text_of(bodycopy)
 if len(text)<60:raise ValueError('공고 본문이 비어 있거나 오류 화면임')
 title=entry['title'];fields={};originals=[];issues=[];proof=[]
 for selector in src.get('title','').split('|'):
  t=s.select_one(selector) if selector else None
  if t is not None and len(flat(t.get_text()))>5:title=flat(t.get_text());break
 if src['kind']=='bizinfo':
  t=s.select_one('.title_area h2,.title_area .title,.view_title,.title')
  for li in body.select('li'):
   label=li.select_one('.s_title')
   if label:
    key=flat(label.get_text());copy=BeautifulSoup(str(li),'html.parser');copy.select_one('.s_title').decompose();fields[key]=text_of(copy)
  # The portal explicitly identifies the agency's original notice.
  for a in s.select('a#barogagi[href]'):
   if a['href'].startswith('http'):
    originals.append(a['href'])
 container=s.select_one(src.get('container',src['body'])) or body
 docs=attachments(container,url)
 if not docs and re.search(r'fn.*(?:down|Down|File)|\.hwp|\.pdf',str(container)):
  issues.append('첨부 연결 자동 확인 못함 — 원문에서 열어 주세요')
 if src['kind']=='dgfca':
  t=s.select_one('.board_tit .tit,.view_tit,.subject,h3.title')
  if t and len(flat(t.get_text()))>10:title=flat(t.get_text())
 # Follow explicit original links, never generic site links as evidence of cross-checking.
 for original in dict.fromkeys(originals):
  try:
   b,_,ou=web.get(original);osoup=soup_of(b)
   ob=osoup.select_one('article,.view_cont,.boardView,.board_view,.bbs_view,.board-view,.view-content,.bbsView_body,.board_detail,.read__content,#contents,main')
   terms=[t for t in re.findall(r'[가-힣]{3,}',title) if t not in ('지원사업','모집공고')]
   if ob and len(text_of(ob))>100 and sum(t in text_of(ob) for t in terms)>=min(2,len(terms)):
    ot=text_of(ob);proof.append({'url':ou,'status':'본문 확인','hash':digest(ot)})
    text+='\n'+ot;docs+=attachments(ob,ou)
   else:proof.append({'url':original,'status':'본문 미확인'})
  except Exception as ex:proof.append({'url':original,'status':'접속 실패'});issues.append('주관기관 원문 접속 실패')
 if src['kind']=='bizinfo' and not originals:issues.append('주관기관 원문 링크 미확인')
 alltext=text;docresults=[];seen=set()
 for doc in docs:
  if doc['url'] in seen:continue
  seen.add(doc['url'])
  d=dict(doc)
  try:
   b,headers,_=web.get(doc['url']);d['hash']=digest(b)
   name=up.unquote(headers.get('Content-Disposition',''))+' '+doc['name']+' '+up.unquote(doc['url'])
   t,w=extract_binary(b,name);d.update(status='확인' if not w else '일부 미확인',issues=w)
   alltext+='\n'+t
  except Exception as ex:d.update(status='미확인',issues=[type(ex).__name__+': '+str(ex)[:130]])
  if d['status']!='확인':issues.append('첨부 미확인: '+doc['name'])
  docresults.append(d)
 # Extract contextual source lines, including the attachments. No invented applicant verdict.
 facts={k:snippets(alltext,p) for k,p in FIELDS.items()}
 overview=fields.get('사업개요','');period=fields.get('신청기간','') or facts['period']
 bullets=re.findall(r'☞\s*([^☞]+)',overview)
 if bullets:facts['audience']=tidy(bullets[0])[:650]
 if len(bullets)>1:facts['benefit']=tidy(bullets[1])[:650]
 attachment_period=facts['period'];facts['period']=period[:650]
 startdate,deadline,deadline_at=schedule(period,title)
 # Conflicting portal / attachment date ranges must not become a confident deadline.
 ends={schedule(line)[1] for line in attachment_period.splitlines() if schedule(line)[1]}
 if deadline:ends.add(deadline)
 if len(ends)>1:
  issues.append('접수 기간이 여러 개이거나 서로 다름 — 원문 일정 대조 필요');deadline='';deadline_at=''
  facts['period']=period[:300]+'\n추가 일정 발췌: '+attachment_period[:350]
 title=flat(title).removesuffix(' 찜하기');categories=[k for k,p in CATEGORIES.items() if re.search(p,title+' '+overview+' '+text,re.I)]
 if src.get('category') and src['category'] not in categories:categories.append(src['category'])
 if not categories:categories=['법인·경영'];issues.append('분야 자동분류 불확실 — 상세 확인 필요')
 types=[]
 for typ,pat in [('융자',r'융자|대출'),('보증',r'보증'),('지원금',r'지원금|보조금|사업화\s*자금|사업비\s*지원'),('서비스·공간',r'컨설팅|교육|대관|공간|입주|멘토링|서비스')]:
  if re.search(pat,title+' '+facts['benefit']):types.append(typ)
 if not types:types=['지원 방식 확인 필요']
 status='접수 상태 확인 필요'
 if deadline:status='마감' if deadline<now().date().isoformat() else '접수 예정' if startdate>now().date().isoformat() else '접수 기간 중'
 if deadline_at and dt.datetime.fromisoformat(deadline_at)<now():status='마감'
 if re.search(r'예산\s*소진',title):status='예산 소진 공지'
 if re.search(r'선정.*결과|선정.*발표|결과.*발표|심의.*결과|합격자',title):status='결과 발표'
 if re.search(r'마감|종료|중단',title) and not re.search(r'마감\s*연장',title):status='종료 안내'
 closed=status in ('마감','결과 발표','종료 안내','예산 소진 공지')
 previous_docs={x['name']:x.get('hash','') for x in old.get('attachments',[])}
 fingerprint=digest(json.dumps({'body':text,'docs':[(x['name'],x.get('hash') or previous_docs.get(x['name'],'')) for x in docresults]},sort_keys=True,ensure_ascii=False))
 changed=bool(old.get('hash') and old['hash']!=fingerprint)
 history=list(old.get('history',[]))
 if changed:history.append({'at':stamp(),'from':old['hash'],'to':fingerprint,'reason':'본문·원문·첨부 변경'})
 summary=flat(overview.split('☞')[0])[:280] if overview else ''
 if not summary and facts['benefit']:summary=flat(facts['benefit'].split('\n')[0])[:180]
 checks={k:bool(v) for k,v in facts.items()}
 for k,label in [('audience','신청 자격'),('exclusions','제외 조건'),('copay','자부담/금리'),('period','접수 기간')]:
  if not facts[k]:issues.append(label+' 자동 확인 못함')
 if not re.search(r'\d{1,2}\s*[:시]\s*\d{0,2}',period):issues.append('접수 마감 시각 원문 확인 필요')
 return dict(entry,title=title,source=src['name'],categories=categories,summary=summary,**facts,
  deadline=deadline,deadlineAt=deadline_at,status=status,closed=closed,types=types,attachments=docresults,originals=proof,
  issues=list(dict.fromkeys(issues)),checks=checks,hash=fingerprint,history=history,
  firstSeen=old.get('firstSeen') or stamp(),checkedAt=stamp(),changedAt=stamp() if changed else old.get('changedAt',''),
  change='변경' if changed else old.get('change','신규'),lastError='')

def load(path,default):
 if not path.exists():return default
 return json.loads(path.read_text(encoding='utf8'))
def save(path,obj):
 path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+'.tmp')
 tmp.write_text(json.dumps(obj,ensure_ascii=False,separators=(',',':')),encoding='utf8');tmp.replace(path)

def save_state(out,state):
 # Per-notice files avoid the GitHub single-file size limit as history accumulates.
 (out/'records').mkdir(parents=True,exist_ok=True)
 for url,record in state['notices'].items():
  p=out/'records'/(digest(url)+'.json')
  content=json.dumps(record,ensure_ascii=False,separators=(',',':'))
  if not p.exists() or p.read_text(encoding='utf8')!=content:save(p,record)
 save(out/'state.json',{**state,'notices':{},'catalogFormat':'files'})

def edition(state,finished):
 today=finished.date();publish=dt.datetime.combine(today,dt.time(8,30),KST)
 # After the morning cutoff, prepare TOMORROW instead of publishing a partial midday replacement.
 if finished.hour>=8:publish+=dt.timedelta(days=1)
 items=[]
 for v in state['notices'].values():
  if not v.get('checkedAt'):continue
  item={k:x for k,x in v.items() if k not in ('hash','history','closed')}
  # Keep changes/closure notices visible for 14 days; retain ALL older records in catalog state.
  last=v.get('changedAt') or v.get('firstSeen','')
  if v.get('status')=='결과 발표':continue
  if v.get('closed') and last[:10]<(today-dt.timedelta(days=14)).isoformat():continue
  if v.get('deadline') and v['deadline']<today.isoformat() and not v.get('changedAt'):continue
  items.append(item)
 def priority(x):
  t=x['title']+' '+x.get('audience','')
  return (12 if '대구' in t else 0)+(8 if re.search(r'철거|부동산|건축|인테리어|소프트웨어|플랫폼|무용|공연|정책자금|경영',t) else 0)
 items.sort(key=lambda x:(x.get('status') in ('마감','결과 발표','종료 안내'),-priority(x),-(int(re.sub(r'\D','', (x.get('changedAt') or x['firstSeen'])[:19])))))
 sources=list(state['sources'].values())
 return {'publishedOn':publish.date().isoformat(),'publishAt':publish.isoformat(),'researchedAt':finished.isoformat(timespec='seconds'),
  'items':items,'sources':sources,'pending':len(state['pending']),
  'partial':bool(state['pending']) or any(x.get('status')!='목록 확인' for x in sources),
  'method':'공식 본문·첨부의 규칙 기반 추출. 신청 자격 확정/법률 판단이 아닙니다. 미확인 항목은 원문 확인이 필요합니다.'}

def run(args):
 out=pathlib.Path(args.output);state=load(out/'state.json',{'schema':1,'notices':{},'pending':{},'sources':{}})
 if state.get('catalogFormat')=='files':
  for f in (out/'records').glob('*.json'):
   n=load(f,{});state['notices'][n['url']]=n
 srcs=load(HERE/'sources.json',[])
 if args.sources:srcs=[s for s in srcs if s['id'] in args.sources.split(',')]
 web=Web(args.seconds);started=stamp()
 def scan(src):
  prev=state['sources'].get(src['id'],{});health={'id':src['id'],'name':src['name'],'url':src['url'].format(page=1),
   'scope':src['scope'],'lastAttempt':started,'lastSuccess':prev.get('lastSuccess',''),'status':'목록 확인',
   'cursor':prev.get('cursor',1),'cycleCompletedAt':prev.get('cycleCompletedAt',''),'discovered':0,'errors':[]}
  entries={};signatures=set();cursor=health['cursor']
  # Always overlap latest pages; remaining pages advance persistently, including the initial backfill.
  pages=list(dict.fromkeys(list(range(1,min(args.pages,25)+1))+list(range(cursor,cursor+args.pages))))
  try:
   for page in pages:
    b,_,u=web.get(src['url'].format(page=page));s=soup_of(b);links=list_links(src,s,u)
    if not links:
     if page==1:raise ValueError('목록 구조 변경 또는 빈 응답 — 새 공고 없음으로 판단하지 않음')
     health.update(cursor=1,cycleCompletedAt=stamp());break
    sig=digest('|'.join(x['url'] for x in links))
    if sig in signatures:
     health.update(cursor=1,cycleCompletedAt=stamp());break
    signatures.add(sig)
    for e in links:entries[e['url']]=e
    if page>=cursor:health['cursor']=page+1
   health['lastSuccess']=stamp()
   if health['cursor']!=1 and not health['cycleCompletedAt']:health['status']='초기 대조 중'
  except Exception as ex:health['status']='조회 실패';health['errors'].append(type(ex).__name__+': '+str(ex)[:160])
  health['discovered']=len(entries);return src,health,list(entries.values())
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
  for src,h,entries in pool.map(scan,srcs):
   state['sources'][src['id']]=h
   for rank,e in enumerate(entries):state['pending'][e['url']]={**e,'listedAt':started,'listRank':rank}
 # Daily re-check all active / unknown notices, plus a rolling weekly pass of closed notices.
 for url,n in state['notices'].items():
  if n['sourceId'] not in {s['id'] for s in srcs}:continue
  if not n.get('closed') or int(digest(url)[:8],16)%7==now().weekday():
   state['pending'].setdefault(url,{k:n[k] for k in ('url','title','sourceId')})
 sources={s['id']:s for s in srcs}
 # Interleave sources: a large national portal must not starve local/art sources.
 queues={sid:[] for sid in sources}
 for e in state['pending'].values():
  if e['sourceId'] in queues:queues[e['sourceId']].append(e)
 for q in queues.values():q.sort(key=lambda e:(e.get('listedAt')!=started,e.get('listRank',999999)))
 jobs=[]
 for i in range(max((len(q) for q in queues.values()),default=0)):
  jobs.extend(q[i] for q in queues.values() if len(q)>i)
 def one(e):
  try:return e,detail(web,sources[e['sourceId']],e,state['notices'].get(e['url'],{})),''
  except Exception as ex:return e,None,type(ex).__name__+': '+str(ex)[:180]
 done=0
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
  # Batches save progress, so a cancelled/cloud time-limited run resumes without losing the backlog.
  for offset in range(0,len(jobs),8):
   if web.expired():break
   for e,record,error in pool.map(one,jobs[offset:offset+8]):
    if record:
     state['notices'][e['url']]=record;state['pending'].pop(e['url'],None);done+=1
     h=state['sources'][e['sourceId']];h['checked']=h.get('checked',0)+1
     h['unreadAttachments']=h.get('unreadAttachments',0)+sum(a['status']!='확인' for a in record['attachments'])
    else:
     h=state['sources'][e['sourceId']];h['status']='일부 확인 실패'
     if error not in h['errors']:h['errors'].append(error)
     if e['url'] in state['notices']:state['notices'][e['url']]['lastError']=error
   save_state(out,state)
 finished=now();state.update(lastRun=finished.isoformat(timespec='seconds'))
 save_state(out,state)
 feed=load(out/'feed.json',{'schema':1,'editions':[]})
 new=edition(state,finished)
 # An all-source outage does not replace the last useful edition with an empty success.
 if new['items'] and done:
  feed['editions']=[e for e in feed['editions'] if e.get('publishAt')!=new['publishAt']]+[new]
  feed['editions']=sorted(feed['editions'],key=lambda e:e['publishAt'])[-3:]
 feed['health']={'lastAttempt':started,'finishedAt':stamp(),'sources':list(state['sources'].values()),'pending':len(state['pending'])}
 save(out/'feed.json',feed)
 report={'startedAt':started,'finishedAt':stamp(),'checked':done,'catalog':len(state['notices']),'pending':len(state['pending']),
  'scheduledFor':new['publishAt'],'sources':[{k:v for k,v in s.items() if k!='errors'} for s in state['sources'].values()]}
 save(out/'runs'/((started[:19].replace(':','-'))+'.json'),report)
 print(json.dumps(report,ensure_ascii=False))
 return 0 if done or not jobs else 2

if __name__=='__main__':
 sys.stdout.reconfigure(encoding='utf8')
 p=argparse.ArgumentParser();p.add_argument('--output',default='support-data');p.add_argument('--seconds',type=int,default=1800)
 p.add_argument('--pages',type=int,default=12);p.add_argument('--sources',default='')
 sys.exit(run(p.parse_args()))
