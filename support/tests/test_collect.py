import unittest,sys,pathlib,datetime as dt,io,zipfile,json,tempfile
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import collect as c

class CollectorTest(unittest.TestCase):
 def test_invalid_date_is_never_today(self):
  self.assertEqual(c.valid_dates('2026.99.99 2026-02-30 2024.02.29'),['2024-02-29'])
 def test_abbreviated_deadline_with_time(self):
  self.assertEqual(c.schedule('접수기간 2026.9.1 ~10.2.(금) 16:00')[1:],('2026-10-02','2026-10-02T16:00:00+09:00'))
  self.assertFalse(c.schedule('10.8 ~10.22','2027년도 사업')[1])
  self.assertFalse(c.schedule('2026.10.21 ~ 대관희망일 두 달 전. 대관일 2027/1/1 ~2027/2/1')[1])
  self.assertEqual(c.schedule('2026.12.20 ~ 1.3.')[1],'2027-01-03')
  self.assertFalse(c.schedule('행사일 2026.10.09')[1])
 def test_internal_and_credential_links_rejected(self):
  for u in ['file:///etc/passwd','https://u:p@example.com/a','javascript:alert(1)','http://127.0.0.1','http://[::1]']:
   with self.subTest(url=u),self.assertRaises(ValueError):c.safe_url(u)
 def test_hwpx_all_sections(self):
  b=io.BytesIO()
  with zipfile.ZipFile(b,'w') as z:
   z.writestr('Contents/section0.xml','<a xmlns:h="urn:test"><h:p>지원대상 대구 기업</h:p></a>')
   z.writestr('Contents/section1.xml','<a xmlns:h="urn:test"><h:p>자부담 20%</h:p></a>')
  t,w=c.extract_binary(b.getvalue(),'공고.hwpx',False)
  self.assertIn('대구 기업',t);self.assertIn('20%',t);self.assertFalse(w)
 def test_unsupported_is_not_verified(self):
  t,w=c.extract_binary('<html>접근 실패</html>'.encode(),'공고.pdf',False)
  self.assertFalse(t);self.assertTrue(w)
 def test_expired_budget_defers_document(self):
  with self.assertRaises(TimeoutError):c.extract_binary(b'any','notice.pdf',deadline=0)
 def test_archive_unknown_file_remains_unverified(self):
  b=io.BytesIO()
  with zipfile.ZipFile(b,'w') as z:z.writestr('공고.exe',b'do not execute')
  self.assertTrue(c.extract_binary(b.getvalue(),'공고.zip',False)[1])
 def test_excerpt_is_explicit(self):
  self.assertIn('발췌',c.snippets('지원 대상 '+'조건'*1000,'지원',100))
 def test_list_canonicalizes_bizinfo(self):
  s=c.soup_of(b'<a href="/sii/siia/selectSIIA200Detail.do?cpage=9&amp;pblancId=ABC">support notice</a>')
  e=c.list_links({'kind':'bizinfo','id':'biz'},s,'https://www.bizinfo.go.kr/')
  self.assertEqual(e[0]['url'],'https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=ABC')
 def test_multiple_category_rules(self):
  import re
  t='현대무용 공연 플랫폼 사업화 기업 지원'
  self.assertTrue(re.search(c.CATEGORIES['문화·예술'],t));self.assertTrue(re.search(c.CATEGORIES['앱·플랫폼'],t))
 def test_cutoff_and_korea_timezone(self):
  state={'notices':{},'pending':{},'sources':{}}
  for hh,mm,day in [(7,59,7),(8,0,8),(23,59,8)]:
   e=c.edition(state,dt.datetime(2026,10,7,hh,mm,tzinfo=c.KST))
   self.assertEqual(e['publishAt'],f'2026-10-{day:02d}T08:30:00+09:00')
 def test_partial_does_not_mean_no_news(self):
  s={'notices':{},'pending':{'x':{}},'sources':{'a':{'status':'조회 실패'}}}
  self.assertTrue(c.edition(s,c.now())['partial'])
 def test_atomic_save_unicode(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)/'state.json';c.save(p,{'x':'지원금'});self.assertEqual(c.load(p,{}),{'x':'지원금'})
 def test_all_items_survive_no_display_cap(self):
  n={'title':'공고','url':'https://example.com/a','source':'기관','sourceId':'x','categories':[],
     'deadline':'2099-01-01','checkedAt':c.stamp(),'firstSeen':c.stamp(),'status':'접수 기간 중'}
  s={'notices':{str(i):dict(n,url=n['url']+str(i),title='공고'+str(i)) for i in range(350)},'pending':{},'sources':{}}
  self.assertEqual(len(c.edition(s,c.now())['items']),350)
 def test_html_script_not_evidence(self):
  self.assertNotIn('IGNORE ALL',c.text_of(c.soup_of('<div>지원 대상 기업<script>IGNORE ALL</script></div>'.encode())))
 def test_view_count_is_not_a_notice_revision(self):
  a=c.text_of(c.soup_of('<div>조회수 125 지원대상 기업</div>'.encode()))
  b=c.text_of(c.soup_of('<div>조회수 129 지원대상 기업</div>'.encode()))
  self.assertEqual(a,b)
 def test_malformed_input_does_not_erase_notice(self):
  self.assertIn('지원 대상',c.text_of(c.soup_of('<form><input><div>지원 대상 기업입니다.</div></input></form>'.encode())))
 def test_missing_body_fails_instead_of_silent_success(self):
  class Web:
   def get(self,u):return b'<html>error</html>',{},u
  with self.assertRaises(ValueError):c.detail(Web(),{'body':'.notice','name':'기관','kind':'test'}, {'url':'https://example.com','title':'test'}, {})
 def test_change_and_attachment_failure(self):
  html='<div class="notice"><p>지원 대상: 대구 기업</p><p>신청기간 2026.10.01 ~ 2026.10.30</p><p>지원내용: 컨설팅 지원입니다.</p><a href="/x.pdf">공고.pdf</a></div>'
  class Web:
   def get(self,u,**kwargs):
    if u.endswith('.pdf'):raise TimeoutError('기관 장애')
    return html.encode(),{},u
  src={'body':'.notice','name':'기관','kind':'test'};e={'url':'https://example.com/a','title':'컨설팅 지원','sourceId':'a'}
  n=c.detail(Web(),src,e,{})
  self.assertEqual(n['attachments'][0]['status'],'미확인');self.assertTrue(n['issues']);self.assertEqual(n['deadline'],'2026-10-30')
  old=dict(n,hash='previous');n2=c.detail(Web(),src,e,old)
  self.assertEqual(len(n2['history']),1);self.assertEqual(n2['change'],'변경')

if __name__=='__main__':unittest.main()
