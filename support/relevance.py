"""회사 업무 관련성 선별. 수집 원본은 보존하며 노출 여부만 결정한다."""
import re, datetime as dt

POLICY = 2
AREAS = ['철거·인테리어', '부동산·경영 컨설팅', '현대무용·공연기획', '부동산 앱·플랫폼']

def classify(item):
 title = str(item.get('title',''))
 audience = str(item.get('audience',''))
 core = title+' '+audience
 evidence = core+' '+str(item.get('summary',''))+' '+str(item.get('benefit',''))
 def has(pattern, text=evidence): return bool(re.search(pattern,text,re.I))
 # 단어가 본문 메뉴/기관 이름에 우연히 등장한 것을 관련 근거로 쓰지 않는다.
 if has(r'선정.{0,12}(결과|발표)|선발.{0,12}결과|합격자|심의.{0,12}결과|채용\s*(공고|시험)|입찰\s*공고|결과\s*(안내|공고|보고)|대상자\s*발표|심사\s*결과|교육생|훈련.*컨설팅|특강|어워즈|통합\s*공고|ACADEMY|아카데미|설명회|세미나',title):
  return {'policy':POLICY,'eligible':False,'reason':'지원 신청 공고 아님','categories':[],'score':0}
 unrelated = r'의료|헬스케어|바이오|의약|병원|의료기기|반도체|이차전지|배터리|자동차|모빌리티|농업|농식품|농산|수산|축산|조선|항공|우주|게임|웹툰|애니메이션|음악|음반|오케스트라|성악|합창|미술|갤러리|문학|출판|공예|패션|섬유|뷰티|화장품|푸드테크|식품|핀테크|FINTECH|원자력|국방|방산|로봇|재난안전|기술거래|입점|팝업스토어|창업제품|수출|도로교통|도로공사|자율주행|드론|스마트물류|트레일|레시피|디자인출원|벤처나라'
 if has(unrelated,title) and not has(r'철거|인테리어|현대\s*무용|컨템포러리|프롭테크|부동산',title):
  return {'policy':POLICY,'eligible':False,'reason':'다른 업종 전용 공고','categories':[],'score':0}
 if has(r'(주관기관|운영기관|수행기관).{0,10}모집|액셀러레이터.*\(보육사\).*공모|보육사.*공모',title):
  return {'policy':POLICY,'eligible':False,'reason':'지원받을 기업 모집 아님','categories':[],'score':0}
 categories=[];reasons=[];score=0
 if has(r'철거|해체공사|인테리어|리모델링|실내건축',core):
  categories.append(AREAS[0]);reasons.append('철거·실내건축 관련');score+=90
 if has(r'부동산|프롭테크|빈집|도시재생|경영\s*컨설팅|컨설팅\s*(기업|업체|기관)|경영\s*자문',core):
  categories.append(AREAS[1]);reasons.append('부동산·컨설팅 관련');score+=80
 dance=has(r'현대\s*무용|컨템포러리|안무|무용',core) or has(r'무용|안무|컨템포러리',str(item.get('discipline','')))
 if not dance and has(r'예술인.*창작대관료\s*지원',title) and has(r'예술인|예술단체',audience) and has(r'창작발표|공연',str(item.get('benefit',''))):dance=True
 if dance and not (has(r'한국\s*무용|전통\s*무용|발레',title) and not has(r'현대\s*무용|컨템포러리|안무',core)):
  categories.append(AREAS[2]);reasons.append('현대무용 활동에 연결되는 무용·안무 지원');score+=90
 prop=has(r'부동산|프롭테크|공간정보|건설\s*플랫폼|철거\s*플랫폼',core)
 dev=has(r'앱|플랫폼|소프트웨어|디지털|개발|데이터|AI|SW',core)
 if prop and dev:
  categories.append(AREAS[3]);reasons.append('부동산 기술·플랫폼 개발');score+=100
 # 업종 제한 없는 자금/사업화는 실제 회사의 공통 수요로 남긴다.
 # 다른 산업의 기업 지원을 '기업' 단어 하나로 포함하지 않는다.
 general=has(r'정책자금|경영안정|운전자금|창업\s*(기업|사업화)|소상공인|중소기업|업종\s*(무관|제한\s*없)',core)
 restricted=has(unrelated,core) or has(r'제조|수출\s*(기업|중소)|여성\s*(기업|창업)|농촌|어업|관광\s*(기업|사업)',core)
 benefit=has(r'자금|융자|보증|지원|사업화|컨설팅',title)
 if not categories and general and benefit and not restricted:
  categories.append(AREAS[1]);reasons.append('회사 공통 자금·경영 지원 후보');score+=35
 # 명시된 타 지역 전용 공고는 기본 목록에서 제외. 원본은 계속 수집한다.
 region=re.match(r'^\s*\[([^\]]+)\]',title)
 if region and has(r'서울|부산|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|제주|충청|전라',region[1]) and not has(r'대구',region[1]) and not has(r'전국|지역\s*무관',audience):
  return {'policy':POLICY,'eligible':False,'reason':'다른 지역 지정 공고','categories':[],'score':0}
 if has(r'서초|서대문구|강남|구미|대전광역시|\[대구\].{0,3}(수성구|북구|서구|중구|남구|달서구|달성군|군위군)',title) and not has(r'전국|지역\s*무관',audience):
  return {'policy':POLICY,'eligible':False,'reason':'다른 지역 지정 공고','categories':[],'score':0}
 if has(r'대구|전국|지역\s*무관',core):score+=15
 return {'policy':POLICY,'eligible':bool(categories),'reason':' · '.join(reasons) if categories else '업무 관련 근거 부족', 'categories':categories,'score':score}

def select(items):
 selected=[]
 today=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()
 for record in items:
  if record.get('deadline') and record['deadline']<today.isoformat() and not record.get('changedAt'):continue
  title=record.get('title','');year=re.search(r'20\d{2}',title);end=re.search(r'[~∼～]\s*(\d{1,2})[./월]\s*(\d{1,2})',title)
  if year and int(year[0])<today.year and not (record.get('deadline','')>=today.isoformat()):continue
  if year and end and not record.get('changedAt'):
   try:
    if dt.date(int(year[0]),int(end[1]),int(end[2]))<today:continue
   except ValueError:pass
  fit=classify(record)
  if not fit['eligible']:continue
  selected.append({**record,'categories':fit['categories'],'relevance':fit})
 selected.sort(key=lambda n:(n.get('status') in ('마감','결과 발표','종료 안내','예산 소진 공지'),-n['relevance']['score'],n.get('deadline') or '9999',n.get('title','')))
 return selected


def research_priority(entry):
 """조사 순서만 정한다. 낮은 순위도 원본/대기열에서 삭제하지 않는다."""
 title=str(entry.get('title',''))
 year=re.search(r'20\d{2}',title)
 if year and int(year[0])<dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).year:return 3
 fit=classify({'title':title})
 if fit['eligible']:return 0 if '대구' in title or re.search(r'현대무용|철거|프롭테크|부동산',title) else 1
 if fit['reason'] in ('지원 신청 공고 아님','지원받을 기업 모집 아님','다른 지역 지정 공고','다른 업종 전용 공고'):return 3
 if re.search(r'공연예술|문예진흥|예술산업보증|창작대관|국제협업',title):return 2
 return 3
