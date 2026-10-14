import unittest,sys,pathlib
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from relevance import classify,AREAS
from matching import funding

class ApplicantTest(unittest.TestCase):
 def names(self,item): return [a['id'] for a in classify(item).get('applicants',[])]
 def test_money_not_gifts(self):
  self.assertFalse(classify({'title':'창업기업 지원','benefit':'사무용품 1종 10만원 상당 무상 지원'})['eligible'])
  self.assertFalse(classify({'title':'현대무용 연습실 지원','benefit':'공간 제공 및 장비 대여'})['eligible'])
  self.assertFalse(classify({'title':'중소기업 컨설팅 지원','benefit':'무료 컨설팅 제공'})['eligible'])
 def test_cash_cost_and_loan(self):
  for benefit in ['제작비 지원','인건비 지원','대관료 지원','장비 구입비 지원']:
   self.assertTrue(classify({'title':'현대무용 지원','benefit':benefit})['eligible'])
  self.assertIn('상환 필요',classify({'title':'중소기업 정책대출'})['finance']['repayment'])
 def test_copay_not_zero_or_exclusion(self):
  r=classify({'title':'프롭테크 사업화 지원','benefit':'사업비 지원','copay':'자부담 50%'})
  self.assertTrue(r['eligible']);self.assertEqual(r['status'],'조건 확인 필요')
 def test_seoul_dance_not_daegu_company(self):
  n={'title':'[서울] 현대무용 제작비 지원','audience':'서울 소재 예술단체'}
  self.assertIn('dance',self.names(n));self.assertNotIn('union',self.names(n))
 def test_other_region_unknown_separate_entity(self):
  n={'title':'[경북] 중소기업 경영안정자금 지원'}
  self.assertEqual(self.names(n),['demolition'])
  self.assertIn('소재지',str(classify(n)['applicants'][0]['checks']))
 def test_residence_not_business_address(self):
  n={'title':'현대무용 제작비 지원','audience':'대구 거주 예술가 개인'}
  self.assertEqual(self.names(n),['person'])
  self.assertIn('거주지',str(classify(n)['applicants'][0]['checks']))
 def test_birth_year_exclusion_does_not_leak_birthdate(self):
  n={'title':'현대무용 청년예술가 지원','audience':'예술가 개인 1992.1.1. 이후 출생자','benefit':'제작비 지원'}
  self.assertFalse(classify(n)['eligible'])
 def test_new_entity_and_personal_history_not_merged(self):
  r=classify({'title':'현대무용 제작비 지원','audience':'개인 및 단체, 공연 실적 3회 필요'})
  checks={a['id']:str(a['checks']) for a in r['applicants']}
  self.assertIn('신생',checks['dance']);self.assertIn('개인 공연',checks['person'])
 def test_revenue_unknown_and_worker_definition(self):
  r=classify({'title':'전국 소상공인 정책자금 지원','audience':'매출 10억원 미만, 상시근로자 5명 미만'})
  self.assertIn('union',self.names({'title':'전국 소상공인 정책자금 지원'}))
  self.assertIn('상시근로자',str(r['applicants']))
 def test_unrelated_platform_not_admitted(self):
  self.assertFalse(classify({'title':'의료 헬스케어 플랫폼 개발 지원','benefit':'개발비 지원'})['eligible'])
  self.assertIn(AREAS[3],classify({'title':'소프트웨어 개발 기업 지원','benefit':'개발비 지원'})['categories'])
 def test_nationwide_not_host_restriction(self):
  self.assertIn('union',self.names({'title':'[서울] 중소기업 자금 지원','audience':'전국 중소기업'}))
 def test_unknown_money_is_not_a_grant(self):
  r=classify({'title':'현대무용 창작지원'})
  self.assertTrue(r['eligible']);self.assertFalse(r['finance']['confirmed'])
 def test_guarantee_only_not_selected(self):
  self.assertFalse(funding({'title':'소상공인 특례보증'})['include'])
  self.assertTrue(funding({'title':'소상공인 특례보증 대출'})['include'])
 def test_seoul_district_is_separate(self):
  self.assertNotIn('dance',self.names({'title':'[서울] 은평구 중소기업 융자지원'}))
  self.assertIn('dance',self.names({'title':'[서울] 강남구 중소기업 융자지원'}))
  self.assertIn('dance',self.names({'title':'[서울] 중소기업 융자지원'}))
 def test_other_art_title_not_attachment_boilerplate(self):
  self.assertFalse(classify({'title':'공연장연계연극대표작육성지원','discipline':'연극 무용 음악','benefit':'제작비 지원'})['eligible'])
