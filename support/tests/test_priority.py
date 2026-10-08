import unittest,sys,pathlib,json,tempfile
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import collect as c
from relevance import classify,research_priority,AREAS

class PriorityTest(unittest.TestCase):
 def test_joint_region_and_other_district(self):
  self.assertTrue(classify({'title':'[대구·경북] 소상공인 경영안정자금 지원'})['eligible'])
  self.assertFalse(classify({'title':'[대구] 수성구 소상공인 경영안정자금 지원'})['eligible'])
  self.assertTrue(classify({'title':'[대구] 동구 소상공인 경영안정자금 지원'})['eligible'])
 def test_dance_evidence_not_generic_art(self):
  self.assertIn(AREAS[2],classify({'title':'공연예술 창작지원','discipline':'지원분야 연극, 무용, 음악'})['categories'])
  self.assertFalse(classify({'title':'공연예술 창작지원','summary':'메뉴 현대무용'})['eligible'])
  self.assertFalse(classify({'title':'음악 전용 공연 지원','discipline':'음악'})['eligible'])
 def test_artist_space_candidate(self):
  self.assertTrue(classify({'title':'예술인 창작대관료 지원','audience':'대구 거주 예술인','benefit':'창작발표 대관료 지원'})['eligible'])
 def test_priority_without_deleting_unrelated(self):
  self.assertLess(research_priority({'title':'[대구] 동구 소상공인 경영안정자금 지원'}),research_priority({'title':'의료 플랫폼 지원'}))
 def test_image_map_links(self):
  s=c.soup_of('<map><area alt="공연예술 창작지원 - 2026.10.8 ~11.5" href="https://artnuri.or.kr/crawler/info/view.do?key=123&amp;encData=A%2BB"></map>'.encode())
  rows=c.list_links({'kind':'arko','id':'arko'},s,'https://www.arko.or.kr/content/6220')
  self.assertEqual(len(rows),1);self.assertEqual(rows[0]['title'],'공연예술 창작지원');self.assertIn('A%2BB',rows[0]['url'])
 def test_refilter_no_early_publication(self):
  with tempfile.TemporaryDirectory() as td:
   p=pathlib.Path(td);(p/'records').mkdir();cut='2026-10-08T07:50:00+09:00'
   old={'url':'https://example.com/old','title':'[대구] 동구 소상공인 지원','checkedAt':cut,'deadline':'2099-01-01'}
   future={**old,'url':'https://example.com/future','checkedAt':'2026-10-08T12:00:00+09:00'}
   c.save(p/'records/old.json',old);c.save(p/'records/new.json',future)
   c.save(p/'feed.json',{'schema':1,'editions':[{'items':[],'researchedAt':cut,'publishAt':'2026-10-08T08:30:00+09:00'}]})
   c.refilter(p);e=c.load(p/'feed.json',{})['editions'][0]
   self.assertEqual([x['url'] for x in e['items']],[old['url']]);self.assertEqual(e['publishAt'],'2026-10-08T08:30:00+09:00');self.assertEqual(e['researchedAt'],cut)
