// Only this dispatcher is exposed to google.script.run. The backend library's
// private state, tokens, helpers and administrative entry points are not exposed.
// Lock/cache/script properties belong to the backend library (same as HTTP).
function doGet(e){
 var channel=String(e&&e.parameter&&e.parameter.channel||'');
 if(!/^[a-f0-9]{32}$/.test(channel))return HtmlService.createHtmlOutput('UNION ONE 자료 연결');
 var t=HtmlService.createTemplateFromFile('Bridge');t.channel=channel;
 return t.evaluate().setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}
function request(payload){
 if(typeof payload!=='string'||payload.length>36000000)throw new Error('Invalid request');
 var p;try{p=JSON.parse(payload);}catch(e){throw new Error('Invalid request');}
 var direct=["api_start", "api_boot", "api_settings", "api_health", "api_refreshMeta", "api_syncNow", "api_opsStatus", "api_opsSetup", "api_opsBackup", "api_opsRestoreCheck", "api_fastTransportSetup", "api_dispatchPush"];
 if(!p||typeof p!=='object'||Array.isArray(p)||direct.indexOf(p.fn)>=0)return JSON.stringify({ok:false,code:'DIRECT_ONLY',notSaved:true,msg:'기존 연결에서 처리해야 하는 요청입니다.'});
 return Workboard.rpcRequest(payload);
}
