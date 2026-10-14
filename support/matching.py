"""공고 발췌와 신청 주체를 대조한다. 후보 선정이며 자격 확정이 아니다.

개인 연락처/등록번호/생년월일/회사 매출을 공개 feed에 넣지 않는다.
미확인 정보는 0 또는 자격 충족으로 간주하지 않는다.
"""
import re

def has(pattern, text):
    return bool(re.search(pattern, text, re.I))

def funding(item):
    text = str(item.get('title', '')) + '\n' + str(item.get('benefit', ''))
    loan = has(r'대출|융자|운전자금|경영안정자금|네트워크론', text)
    grant = has(r'지원금|보조금|장려금|출연금|사업화\s*자금|사업비\s*지원|제작비|창작지원금|인건비|임차료|대관료|구입비|개발비|보험료|수수료|이차보전|이자차액보전|금융비용|이자\s*지원|비용\s*지원|경비.{0,12}(지원|일부)', text)
    if has(r'이자지원|이자차액보전|금융비용|비용\s*지원|수수료', str(item.get('title',''))): loan=False
    noncash = has(r'사무용품|현물|무상\s*(제공|대여)|공간\s*(제공|지원)|입주|장비\s*(대여|제공)|교육|수강|멘토링|컨설팅\s*(제공|지원|참여|신청|서비스|및)|상담|간담회|보증|크레딧|현장맞춤형\s*양성', text)
    if not loan and not grant and noncash:
        return {'include': False, 'kind': '', 'reason': '금전 지원 근거 없음 · 비금전/보증 단독 지원'}
    kind = '지원금·정책대출' if loan and grant else '정책대출' if loan else '지원금·비용 지원' if grant else '금전 지원 여부 확인'
    return {'include': True, 'kind': kind, 'confirmed': loan or grant,
            'repayment': '대출은 상환 필요 · 금리·기간은 원문 확인' if loan else '지원금도 용도·정산·환수 조건 확인' if grant else '지원 방식과 상환 여부 확인'}

def region_of(item):
    title = str(item.get('title', ''))
    audience = str(item.get('audience', ''))
    if has(r'전국|지역\s*(무관|제한\s*없)', audience):
        return '', ''
    # 주관기관 주소/행사 장소를 신청자의 지역 요건으로 쓰지 않는다.
    match = re.search(r'(서울|대구|부산|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|제주)(?:특별시|광역시|특별자치도|도)?(?:\s*[가-힣]+[구군])?\s*(?:에\s*)?(?:거주|소재|지역\s*(?:기업|예술|주민))', audience)
    prefix = re.match(r'\s*\[([^\]]+)\]', title)
    value = match[0] if match else prefix[1] if prefix else ''
    if not value:
        match = re.search(r'(서울|대구|서초|서대문구|강남|구미|대전광역시|화성시|과천시|용인시|수원시|성남시|고양시|안산시|부천시|전주시|청주시|천안시|창원시)', title)
        value = match[0] if match else ''
    return value, 'residence' if '거주' in value else 'location'

def applicant_matches(item, categories, finance):
    title = str(item.get('title', ''))
    audience = str(item.get('audience', ''))
    exclusions = str(item.get('exclusions', ''))
    art = '현대무용·공연기획' in categories
    general = has(r'중소기업|소상공인|정책자금|경영안정|운전자금|업종\s*(무관|제한\s*없)', title+' '+audience)
    ids = []
    if not art: ids.append('union')
    if '철거·인테리어' in categories or general: ids.append('demolition')
    if art: ids.extend(['dance', 'person'])
    if not art and has(r'예비창업|개인\s*(신청|창업)|청년\s*창업', title+' '+audience): ids.append('person')
    if general and not art: ids.append('dance')
    names = {'union':'유니온 원 법인','demolition':'유니온원철거','dance':'JH C-WAVE','person':'대표자 개인'}
    region, region_type = region_of(item)
    matches = []
    for key in dict.fromkeys(ids):
        reasons = []
        checks = []
        if key == 'union' and has(r'개인사업자', title) and not has(r'법인', title): continue
        if key in ('person','dance') and has(r'법인사업자|비영리법인\s*만', title+' '+audience): continue
        if key == 'union': reasons.append('대구 동구 사업장 · 관련 사업 운영')
        elif key == 'demolition': checks.append('별도 사업자의 소재지·개업일·매출·근로자 수 확인')
        elif key == 'dance': reasons.append('서울 강남구 · 현대무용 사업자')
        else: checks.append('개인 신청 허용 여부·실제 거주지 확인')
        # 알려진 사업장과 명백히 다른 지역은 해당 주체에서만 제외한다.
        if region and region_type != 'residence' and key in ('union','dance'):
            expected = '대구' if key == 'union' else '서울'
            if expected not in region and not (key == 'dance' and '강남' in region): continue
            district = re.search(r'(?:\]|서울(?:특별시)?|대구(?:광역시)?)\s*([가-힣]{1,4}[구군])(?:\s|\d|$)', title+' '+audience)
            if district and district[1] != ('동구' if key == 'union' else '강남구'): continue
            if key == 'union' and has(r'수성구|북구|서구|중구|남구|달서구|달성군|군위군', title): continue
            if key == 'dance' and has(r'서초|서대문|강북|송파|마포', region+' '+title): continue
        if region:
            checks.append(('거주지·거주기간' if region_type == 'residence' else '소재지')+' 요건: '+region)
        if key == 'person' and not art: checks.append('기존 사업 보유에 따른 창업 지원 제한 확인')
        # 명시적으로 개인만 받는 공고에 법인/단체를 신청 후보로 내놓지 않는다.
        if key != 'person' and has(r'(개인|예술가)\s*만\s*(신청|지원)|예술가\s*개인', audience) and not has(r'개인\s*(또는|및|[,·/])\s*단체', audience): continue
        if key == 'person' and has(r'(법인|단체)\s*만\s*(신청|지원)|개인\s*(신청\s*)?불가', audience): continue
        if key in ('person','dance'):
            # 출생연도 범위가 확실한 개인 공모만 판정. 만 나이는 기준일 미확인 시 추정하지 않는다.
            young = re.search(r'(19\d{2}|20\d{2})\s*[.년/-]\s*\d{1,2}\s*[.월/-]\s*\d{1,2}\s*[.일]?\s*이후\s*출생', audience)
            if key == 'person' and young and int(young[1]) > 1990: continue
            if art:
                checks.append('신생 사업체의 단체 자격·실적 인정 범위 확인' if key=='dance' else '개인 공연 경력·예술활동증명 확인')
        if has(r'매출|소상공인|중소기업|상시\s*(근로|종업)|고용|직원', title+' '+audience): checks.append('매출·공고 기준 상시근로자 수 확인')
        if has(r'창업|업력|설립|개업', title+' '+audience): checks.append('법인 설립일·기존 사업 이력 등 업력 산정 확인')
        if has(r'실적|경력|이력|초연|후속|공연장|비영리|고유번호', title+' '+audience): checks.append('필수 실적·선정 이력·시설·단체 등록 요건 확인')
        if not finance['confirmed']: checks.append('실제 금전 지원인지 원문 확인')
        checks.append('제외 업종·중복 수혜·체납 등 제한 확인')
        matches.append({'id':key,'name':names[key],'status':'조건 확인 필요','reasons':reasons,'checks':list(dict.fromkeys(checks))})
    return matches

def match(item, categories):
    finance = funding(item)
    applicants = applicant_matches(item, categories, finance) if finance['include'] else []
    return {'finance':finance,'applicants':applicants,'status':'조건 확인 필요'}
