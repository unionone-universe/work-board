/* UNION ONE WORK BOARD - 런처 서비스워커
 *
 * 앱 화면(app.html)도 이 저장소에 있습니다.
 * 열 때마다 서버에 "바뀌었나" 를 물어보고, 바뀌었을 때만 새로 받습니다.
 *
 * ★ 화면을 고쳐서 올릴 때마다 아래 CACHE 뒤의 숫자를 하나 올리세요.
 *   index.html 의 APP_VER 도 같은 숫자로 맞춰두면 헷갈리지 않습니다.
 *
 * ────────────────────────────────────────────────────────────
 * 2026-08-29 · 속도
 *
 * 앱을 열 때마다 app.html 225KB 를 통째로 다시 받고 있었습니다.
 * 런처가 주소 끝에 Date.now() 를 붙여 **매번 다른 주소**를 만들었기 때문에
 * 캐시가 한 번도 맞은 적이 없었습니다. 그래서 세 가지가 같이 일어났습니다.
 *
 *   · 열 때마다 225KB 를 새로 내려받았다  (앱이 늦게 뜨던 가장 큰 이유)
 *   · 열 때마다 캐시에 새 칸이 쌓였다      (100번 열면 22MB)
 *   · 캐시가 맞은 적이 없어 오프라인에서는 앱 화면이 아예 안 떴다
 *     (캐시를 못 찾아 런처 껍데기 index.html 을 대신 내주고 있었습니다)
 *
 * 고친 것
 *   ① 런처가 붙이는 v= 를 고정된 판 번호로 바꿨습니다 (index.html)
 *   ② 캐시에 넣을 때 물음표 뒤(?dt=..&v=..)를 떼어내 한 칸만 씁니다
 *   ③ 받아올 때 cache:"no-cache" 로 서버에 "바뀌었나" 만 물어봅니다
 *      안 바뀌었으면 서버가 '그대로다(304)' 한 줄만 보냅니다 — 수백 바이트
 *   ④ 캐시가 있으면 통신을 2.5초까지만 기다립니다
 *
 * ▶ '항상 최신을 확인한다' 는 규칙은 하나도 달라지지 않았습니다.
 *   달라진 것은 안 바뀐 날에 225KB 를 다시 안 받는다는 것뿐입니다.
 * ────────────────────────────────────────────────────────────
 */
const CACHE = 'unionone-launcher-v109';  // 2026-10-07 지원사업 소식 · 수집과 예약 게시

const VERSION=CACHE.split('-').pop();
const NET_WAIT_MS=2500;
const SHELL=['./','./index.html','./app.html','./manifest.webmanifest','./icon-192.png','./icon-512.png','./icon-maskable-192.png','./icon-maskable-512.png','./apple-touch-icon.png','./badge-96.png'];
function cacheKey(request){const u=new URL(typeof request==='string'?request:request.url,self.location.href);return u.origin+u.pathname;}
async function keep(cache,request,response){
  if(!response || !response.ok || response.redirected)return;
  // 이전 HTTP/CDN 저장본을 새 판으로 잘못 고정하지 않는다.
  if(new URL(cacheKey(request)).pathname.endsWith('/app.html')){
    const text=await response.clone().text();
    if(!text.includes('<meta name="uo-version" content="'+VERSION+'">'))return;
  }
  try{await cache.put(cacheKey(request),response.clone());}catch(ignore){}
}
self.addEventListener('install',e=>e.waitUntil((async()=>{
  const cache=await caches.open(CACHE);
  await Promise.all(SHELL.map(async u=>{try{const res=await fetch(new URL(u,self.location.href),{cache:'reload'});await keep(cache,new URL(u,self.location.href).href,res);}catch(ignore){}}));
  await self.skipWaiting();
})()));
self.addEventListener('activate',e=>e.waitUntil((async()=>{
  const keys=await caches.keys();
  await Promise.all(keys.filter(k=>k.startsWith('unionone-launcher-')&&k!==CACHE).map(k=>caches.delete(k)));
  await self.clients.claim();
})()));
function wait(ms){return new Promise(resolve=>setTimeout(()=>resolve(null),ms));}
self.addEventListener('fetch',e=>{
  const url=new URL(e.request.url);
  if(e.request.method!=='GET'||url.origin!==self.location.origin)return;
  let finish;const background=new Promise(resolve=>{finish=resolve;});
  e.waitUntil(background);
  e.respondWith((async()=>{
    try{
      const cache=await caches.open(CACHE),cached=await cache.match(cacheKey(e.request));
      const isApp=url.pathname.endsWith('/app.html');
      const isShell=/\.(html|js|css)$/.test(url.pathname)||url.pathname.endsWith('/');
      // 같은 판 재접속은 기다리지 않는다. 새 판은 항상 네트워크에서 받는다.
      if(cached&&isApp&&url.searchParams.get('v')===VERSION){finish();return cached;}
      const network=fetch(e.request,{cache:'no-cache'}).then(async res=>{
        await keep(cache,e.request,res);return res&&res.ok?res:null;
      }).catch(()=>null).finally(finish);
      if(cached&&!isShell)return cached;
      const fresh=cached?await Promise.race([network,wait(NET_WAIT_MS)]):await network;
      // 앱 요청에 런처 HTML을 돌려주면 iframe이 재귀적으로 열리므로 금지.
      return fresh||cached||Response.error();
    }catch(ignore){finish();return Response.error();}
  })());
});


/* ===================== 폰 알림 (2026-09-01) =====================

   앱을 꺼 두어도 폰 잠금화면에 뜨는 알림을 여기서 그립니다.

   ★ firebase 라이브러리를 여기에 불러오지 않습니다.
     구글이 보내주는 것을 우리가 직접 읽어 그리면 되고,
     그러면 서비스워커가 가벼워지고 라이브러리 판이 바뀌어도 안 깨집니다.

   ★ 이미 앱 창이 열려 있으면 그 창을 앞으로 가져옵니다.
     새 창을 또 열면 로그인부터 다시 하게 됩니다.
================================================================= */

self.addEventListener('push', (e) => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch (err) { d = {}; }

  /* 구글이 보내는 모양이 조금씩 다릅니다. 있는 데서 차례로 꺼냅니다 */
  const n = d.notification || d.data || d || {};
  const title = n.title || '워크보드';
  const body = n.body || n.message || '';
  const link = (d.fcmOptions && d.fcmOptions.link) || n.click_action || './';

  /* ★★ badge 는 icon 과 쓰임이 다릅니다 (2026-09-02).
       icon   펼친 알림의 큰 그림  — 색깔 그대로 나온다
       badge  상태표시줄의 작은 그림 — **모양(투명도)만 쓰고 색은 버린다**

     예전에는 badge 에 icon-96.png 를 주고 있었는데 그 그림은
     **투명한 곳이 하나도 없는 꽉 찬 사각형**이라, 안드로이드가 전체를 하얗게 칠해
     상태표시줄에 **하얀 네모**만 떴습니다.
     badge-96.png 는 바탕이 완전히 투명하고 로고 모양만 남긴 그림입니다
     (_점검/뱃지만들기.js 가 만듭니다). */
  e.waitUntil(self.registration.showNotification(title, {
    body: body,
    icon: './icon-192.png',
    badge: './badge-96.png',
    tag: 'unionone',          /* 같은 표를 달아 알림이 쌓이지 않게 */
    renotify: true,
    data: { url: link }
  }));
});

self.addEventListener('notificationclick', (e) => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || './';

  e.waitUntil((async () => {
    const list = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    /* 이미 열려 있는 창이 있으면 그것을 앞으로 */
    for (const c of list) {
      if (c.url.indexOf(self.registration.scope) === 0 && 'focus' in c) return c.focus();
    }
    if (self.clients.openWindow) return self.clients.openWindow(url);
  })());
});

