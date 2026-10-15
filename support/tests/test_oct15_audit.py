import unittest,datetime as dt
from relevance import classify,select,period_ended,REVIEWED_EXCLUSIONS

class AuditTest(unittest.TestCase):
 def test_changed_closed_notice_not_revived(self):
  self.assertEqual(select([{'title':'현대무용 지원금','deadline':'2020-01-01','changedAt':'2099-01-01'}]),[])
 def test_archived_originals(self):
  for url in REVIEWED_EXCLUSIONS:self.assertFalse(classify({'url':url,'title':'현대무용 제작비 지원'})['eligible'])
 def test_other_industries(self):
  for title,audience in [('소상공인 관광코스 개발 및 굿즈 상품화 지원',''),('중소기업 자금 지원','철강ㆍ금속 분야 기업'),('IoT 설치 지원','중소기업 배출시설 및 방지시설')]:
   self.assertFalse(classify({'title':title,'audience':audience})['eligible'])
 def test_noncash(self):
  for benefit in ['1:1 채용 매칭 지원','안심벨 설치 및 안내문 부착 지원']:
   self.assertFalse(classify({'title':'소상공인 지원','benefit':benefit})['eligible'])
 def test_real_cost_remains(self):
  self.assertTrue(classify({'title':'중소기업 연구인력 현장맞춤형 양성지원','benefit':'연구개발비 1,720만원 지원'})['eligible'])
 def test_uncertain_region_remains(self):
  n=classify({'title':'[충남] 소상공인 카드수수료 지원','benefit':'수수료 지원'})
  self.assertTrue(n['eligible']);self.assertEqual([x['id'] for x in n['applicants']],['demolition'])
 def test_period_range(self):
  day=dt.date(2026,10,15)
  self.assertTrue(period_ended('접수기간 2026. 3. 31.(화) ~ 4. 21.(화) 14:00까지',day))
  self.assertTrue(period_ended('접수마감일 : 2010. 9. 30(목)',day))
  self.assertFalse(period_ended('접수기간 2026.10.01 ~ 11.30',day))
  self.assertFalse(period_ended('접수 시작 2026.10.01',day))
  self.assertFalse(period_ended('접수기간 2026.10.01 ~ 예산 소진 시',day))
  self.assertFalse(period_ended('접수기간 2026.12.01 ~ 1.30',dt.date(2027,1,1)))
  self.assertFalse(period_ended('접수기간 2026.01.01 ~ 2.30',day))
 def test_official_header_deadline(self):
  import collect as c
  from unittest.mock import patch
  class Web:
   def get(self,url,**kw):return html.encode('utf-8'),{},url
  for kind,header in [('arko','시작일 2021.11.02 마감일 2021.11.22'),('dip','기간 2021-11-02 ~ 2021-11-22 등록일 2021-11-02')]:
   html='<div>'+header+'</div><article><h3>현대무용 제작비 지원사업</h3><p>'+('지원대상 현대무용 예술인. 지원내용 제작비 지원. '*5)+'</p></article>'
   n=c.detail(Web(),{'kind':kind,'name':'공식기관','body':'article'},{'url':'https://example.org/notice','title':'현대무용 제작비 지원사업'}, {})
   self.assertEqual(n['deadline'],'2021-11-22');self.assertEqual(n['status'],'마감')

if __name__=='__main__':unittest.main()
