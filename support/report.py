import sys,json,pathlib
p=pathlib.Path(sys.argv[1])/'feed.json'
print('### 지원사업 조사')
if not p.exists():
 print('조사 결과를 만들지 못했습니다. 이전 게시본을 유지합니다.')
else:
 d=json.loads(p.read_text(encoding='utf8'));h=d.get('health',{})
 print('완료 시각:',h.get('finishedAt','미확인'))
 print('\n재시도 대기:',h.get('pending','미확인'),'건\n')
 print('| 기관 | 상태 | 마지막 목록 확인 |\n|---|---|---|')
 for s in h.get('sources',[]):print('|',s['name'],'|',s['status'],'|',s.get('lastSuccess','없음'),'|')
