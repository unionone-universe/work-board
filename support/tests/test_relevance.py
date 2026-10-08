import unittest,sys,pathlib
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from relevance import classify,select,AREAS
class RelevanceTest(unittest.TestCase):
 def test_direct_and_common(self):
  for title,area in [('철거 인테리어 기업 지원',0),('부동산 경영 컨설팅 기업 지원',1),('현대무용 공연기획 지원',2),('프롭테크 플랫폼 개발 지원',3),('전국 중소기업 경영안정자금 지원',1)]:
   with self.subTest(title=title):self.assertIn(AREAS[area],classify({'title':title})['categories'])
 def test_unrelated(self):
  for title in ['의료 헬스케어 플랫폼 창업기업 지원','음악 공연 지원','갤러리 미술 전시 지원','전통무용 지원','발레 공연 지원','[경북] 중소기업 지원','[서초창업스테이션] 소상공인 지원','대전광역시 중소기업 법률상담회 지원','도로공사 창업기업 지원','중소기업 수출 지원','창업기업 지원 통합공고','지원 공고','웹툰 플랫폼 개발 지원']:
   with self.subTest(title=title):self.assertFalse(classify({'title':title})['eligible'])
 def test_restricted_audience(self):
  self.assertFalse(classify({'title':'창업 성장지원','audience':'대구 소재 제조(소재, 부품) 분야 창업기업'})['eligible'])
 def test_national_despite_host(self):
  self.assertTrue(classify({'title':'[서울] 중소기업 자금 지원','audience':'전국 중소기업'})['eligible'])
 def test_no_source_category_shortcut(self):
  self.assertFalse(classify({'title':'일반 모집','categories':['앱·플랫폼'],'summary':'사이트 메뉴 현대무용 부동산'})['eligible'])
 def test_rank_and_preserve(self):
  rows=[{'title':'전국 중소기업 자금 지원','deadline':'2099-01-01'},{'title':'부동산 플랫폼 개발 지원','deadline':'2099-01-01'}]
  got=select(rows);self.assertEqual(got[0]['title'],rows[1]['title']);self.assertNotIn('relevance',rows[0])
 def test_empty_and_expired(self):
  self.assertEqual(select([{'title':'현대무용 지원','deadline':'2000-01-01'}]),[])
  self.assertEqual(select([{'title':'의료 플랫폼 지원'}]),[])
if __name__=='__main__':unittest.main()
