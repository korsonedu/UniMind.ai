import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';
import os from 'node:os';
import { existsSync, mkdirSync } from 'node:fs';
import assert from 'node:assert/strict';
const require = createRequire(import.meta.url);
const runtimePlaywright = path.join(os.homedir(), '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || (existsSync(runtimePlaywright) ? runtimePlaywright : 'playwright'));
const windowsChrome = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const browser = await chromium.launch({ headless: true, ...(process.env.CHROMIUM_PATH || existsSync(windowsChrome) ? { executablePath: process.env.CHROMIUM_PATH || windowsChrome } : {}) });
const base = process.env.PREVIEW_URL || 'http://127.0.0.1:4173';
const user = { id: 12, username: 'native-test', nickname: '原生验证', role: 'student', avatar_url: '/media/avatar.png', has_completed_initial_assessment: true, tour_dismissed_at:'2026-01-01', tour_panel_dismissed_at:'2026-01-01' };
const context = await browser.newContext({ locale:'zh-CN', viewport:{width:390,height:844}, hasTouch:true, isMobile:true, serviceWorkers:'block' });
const errors = [], requests = [];
let token = 'native-initial';
const extraPreferences = new Map();
let videoTicketVersion = 0;
const videoBytes = readFileSync(new URL('../public/demos/demo-knowledge.mp4', import.meta.url));
const course = {id:1,title:'原生视频验证',description:'',album:null,module:null,module_name:'',subject_name:'验证',module_sort_order:0,knowledge_point:null,cover_image:null,video_file:'/media/video.mp4',courseware:null,reference_materials:null,elo_reward:0,ai_outline_enabled:false,sort_order:0,tags:[],progress:null,created_at:'2026-01-01'};
await context.exposeBinding('nativePreferences', async (_, operation, options) => {
  if (options.key !== 'unimind_native_auth_token') { if (operation === 'get') return { value: extraPreferences.get(options.key) || null }; if (operation === 'set') extraPreferences.set(options.key, options.value); if (operation === 'remove') extraPreferences.delete(options.key); return {}; }
  if (operation === 'get') { await new Promise(resolve => setTimeout(resolve, 650)); return { value: token }; }
  if (operation === 'set') token = options.value;
  if (operation === 'remove') token = null;
  return {};
});
await context.addInitScript(() => {
  if (!localStorage.getItem('unimind:server-origin')) localStorage.setItem('unimind:server-origin', 'http://127.0.0.1:8000');
  window.androidBridge = {};
  window.__ws = []; window.__hydrated = false; window.__xhr = []; window.__exitCount = 0; window.__fetch = [];
  const originalFetch = window.fetch;
  window.fetch = function(input, init) { window.__fetch.push({url:String(input), credentials:init?.credentials, headers:init?.headers}); return originalFetch.call(this,input,init); };
  const send = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.send = function(...args) { window.__xhr.push({ credentials:this.withCredentials, hydrated:window.__hydrated }); return send.apply(this,args); };
  window.Capacitor = {
    PluginHeaders:[
      {name:'Preferences',methods:['get','set','remove'].map(name=>({name,rtype:'promise'}))},
      {name:'App',methods:[{name:'addListener',rtype:'callback'},{name:'removeListener',rtype:'promise'},{name:'exitApp',rtype:'promise'}]},
    ],
    nativePromise: async (plugin, method, options) => {
      if (plugin === 'App' && method === 'exitApp') window.__exitCount += 1;
      if (plugin !== 'Preferences') return {};
      const result = await window.nativePreferences(method, options);
      if (method === 'get') window.__hydrated = true;
      if (method === 'set') window.__nativeWrite = options.value;
      return result;
    },
    nativeCallback: (plugin, method, options, callback) => { window.__nativeBack = callback; return 'back-1'; },
  };
  window.WebSocket = class {
    static OPEN = 1; readyState=1;
    constructor(url) { window.__ws.push(url); setTimeout(()=>this.onopen?.({}),0); }
    send() {} close() {}
  };
});
await context.route('**/*', async route => {
  const req = route.request(), url = new URL(req.url());
  if (!url.pathname.startsWith('/api/') && !url.pathname.startsWith('/media/') && url.pathname !== '/health/') return route.continue();
  requests.push({path:url.pathname, origin:url.origin, headers:req.headers(), method:req.method()});
  if (req.method()==='OPTIONS') return route.fulfill({ status:204, headers:{'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'*','Access-Control-Allow-Methods':'GET, POST, PATCH, OPTIONS'} });
  let data = [];
  if (url.pathname === '/api/users/me/') {
    if (!req.headers().authorization) return route.fulfill({status:401,json:{detail:'unauthorized'}});
    data = user;
  } else if (url.pathname === '/api/users/workspace/') data = {available:false,workspace:null,role:null,courses:[],members:[],invites:[],usage:[]};
  else if (url.pathname.includes('/institution/me/features/')) data = {is_platform_admin:false, features:['ai.assistant','study.room','course.video'],institution:null};
  else if (url.pathname === '/api/users/me/password/') data = {status:'ok',token:'native-rotated'};
  else if (url.pathname === '/api/ws-ticket/') data = {ticket:'ws-test-ticket', expires_in:30};
  else if (url.pathname === '/api/media-ticket/') { const path=JSON.parse(req.postData()).path; data={ticket:path==='/media/video.mp4' ? `video-ticket-${++videoTicketVersion}` : 'media-test-ticket',expires_in:300,path}; }
  else if (url.pathname === '/api/courses/') data = {items:[course],total:1,page:1,total_pages:1};
  else if (url.pathname === '/api/courses/1/') data = course;
  else if (url.pathname === '/media/video.mp4') return route.fulfill({contentType:'video/mp4',headers:{'Access-Control-Allow-Origin':'*'},body:videoBytes});
  else if (url.pathname === '/health/') data = {status:'ok',database:true,cache:true};
  else if (url.pathname.startsWith('/media/')) return route.fulfill({contentType:'image/gif',headers:{'Access-Control-Allow-Origin':'*'},body:Buffer.from('R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==','base64')});
  else if (url.pathname === '/api/notes/references/') data = {note_ids:[]};
  else if (url.pathname === '/api/users/learning/access/') data = {is_course_student:true,cohort:null,addons:[],ai_usage:{unlimited:true,configured:true,remaining:null,base_remaining:null,addon_remaining:0}};
  else if (url.pathname.includes('unread')) data = {count:0};
  else if (url.pathname === '/api/ai/bots/') data = [{id:1,name:'小宇',bot_type:'planner',is_active:true}];
  else if (url.pathname === '/api/ai/chat/stream/') return route.fulfill({contentType:'text/event-stream',headers:{'Access-Control-Allow-Origin':'*'},body:'data: '+JSON.stringify({done:true,full_content:'原生流式鉴权验证成功',message_id:13})+'\n\n'});
  else if (url.pathname.includes('/ai/')) data = [];
  return route.fulfill({json:data, headers:{'Access-Control-Allow-Origin':'*'}});
});
const page=await context.newPage();
page.on('pageerror', error=>errors.push(error.message));
page.on('console', message=>{if(message.type()==='error') errors.push(message.text());});
try {
  await page.goto(`${base}/settings?section=account`);
  await page.getByRole('button',{name:'修改密码',exact:true}).click();
  await page.getByLabel('当前密码',{exact:true}).waitFor();
  assert.equal(new URL(page.url()).pathname,'/settings','hydration must not redirect to login');
  assert.ok((await page.evaluate(()=>window.__xhr)).every(r=>r.hydrated && !r.credentials),'XHR waits for Preferences and omits cookies');
  assert.equal(requests.find(r=>r.path==='/api/users/me/' && r.method==='GET').headers.authorization,'Token native-initial');
  await page.waitForFunction(()=>window.__ws.some(url=>url.includes('?ticket=ws-test-ticket')));
  await page.waitForFunction(()=>[...document.images].some(image=>image.src.includes('/media/avatar.png?media_token=media-test-ticket') && image.complete && image.naturalWidth > 0));
  await page.getByLabel('当前密码',{exact:true}).fill('previous-password');
  await page.getByLabel('新密码',{exact:true}).fill('new-password');
  await page.getByRole('button',{name:'更新密码',exact:true}).click();
  await page.waitForFunction(()=>document.body.textContent.includes('密码已更新'));
  await page.waitForFunction(()=>window.__nativeWrite === 'native-rotated');
  assert.equal(token,'native-rotated','password rotation updates Preferences');
  const stored = await page.evaluate(()=>JSON.parse(localStorage.getItem('auth-storage')));
  assert.deepEqual(Object.keys(stored.state),['user'],'browser persistence contains only user');
  await page.reload();
  await page.getByRole('button',{name:'修改密码',exact:true}).click();
  await page.getByLabel('当前密码',{exact:true}).waitFor();
  assert.equal(requests.filter(r=>r.path==='/api/users/me/' && r.method==='GET').at(-1).headers.authorization,'Token native-rotated');
  await page.clock.install();
  await page.goto(`${base}/course/1`);
  await page.waitForFunction(()=>document.querySelector('video')?.readyState>=1);
  await page.locator('video').evaluate(async video=>{video.muted=true;video.currentTime=3;await video.play();});
  await page.waitForFunction(()=>!document.querySelector('video').paused);
  const originalVideo = await page.locator('video').evaluate(video=>({src:video.currentSrc,time:video.currentTime}));
  await page.clock.fastForward(240_500);
  await page.waitForFunction(src=>{const video=document.querySelector('video');return video?.currentSrc!==src && video?.readyState>=1 && !video.paused && video.currentTime>=2.5;},originalVideo.src);
  await page.clock.resume();
  await page.goto(`${base}/xiaoyu`);
  await page.getByRole('textbox',{name:'和小宇对话'}).fill('验证原生流式请求');
  await page.getByRole('button',{name:'发送消息',exact:true}).click();
  await page.getByText('原生流式鉴权验证成功',{exact:true}).waitFor();
  const sse = await page.evaluate(()=>window.__fetch.find(r=>r.url.includes('/ai/chat/stream/')));
  assert.equal(sse.credentials,'omit');
  assert.equal(sse.headers.Authorization,'Token native-rotated');
  assert.equal(sse.headers['X-CSRFToken'],undefined);
  await page.goto(`${base}/settings?section=general`);
  await page.getByRole('button',{name:'更改服务器地址',exact:true}).click();
  await page.evaluate(()=>window.__nativeBack({canGoBack:true}));
  await page.getByRole('dialog').waitFor({state:'hidden'});
  await page.getByRole('button',{name:'更改服务器地址',exact:true}).click();
  await page.getByRole('button',{name:'测试连接',exact:true}).click();
  await page.getByText('连接成功：',{exact:false}).waitFor();
  await page.getByLabel('服务端地址（Origin）').fill('http://192.168.1.99:8000');
  const switched = page.waitForEvent('load');
  await page.getByRole('button',{name:'保存并应用',exact:true}).click();
  await switched;
  await page.waitForURL('**/login');
  await page.waitForFunction(()=>window.__hydrated && typeof window.__nativeBack === 'function');
  assert.equal(token,null,'switching server deletes old token before reload');
  assert.equal(await page.evaluate(()=>localStorage.getItem('unimind:server-origin')),'http://192.168.1.99:8000');
  await page.evaluate(()=>{ window.__nativeBack({canGoBack:false}); window.__nativeBack({canGoBack:false}); });
  await page.waitForFunction(()=>window.__exitCount===1);
  assert.ok(!requests.some(r=>r.origin==='http://192.168.1.99:8000' && r.headers.authorization),'old credentials never reach new server');
  for(const r of requests.filter(r=>r.path.startsWith('/api/') && r.method!=='OPTIONS')) {
    assert.equal(r.headers['x-csrftoken'],undefined,'native request has no CSRF header');
    assert.equal(r.headers.cookie,undefined,'native request has no cookie');
  }
  const web = await browser.newContext({ locale:'zh-CN', viewport:{width:390,height:844}, hasTouch:true, serviceWorkers:'block' });
  const webRequests = [];
  let webAuthenticated = false;
  await web.addInitScript(() => {
    window.__webXhr = [];
    const original = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.send = function(...args) { window.__webXhr.push(this.withCredentials); return original.apply(this,args); };
  });
  await web.route('**/accounts/session/', route=>route.fulfill({json:{}}));
  await web.route('**/api/**', route=>{
    const path = new URL(route.request().url()).pathname;
    webRequests.push({path,headers:route.request().headers()});
    if (path === '/api/users/login/') webAuthenticated = true;
    if (path === '/api/users/me/' && !webAuthenticated) return route.fulfill({status:401,json:{detail:'anonymous'}});
    const data = path==='/api/csrf/' ? {csrf_token:'web-csrf'}
      : path==='/api/users/login/' ? {user,token:'web-response-token'}
      : path==='/api/users/me/' ? user
      : path.includes('/institution/me/features/') ? {features:['ai.assistant'],is_platform_admin:false,institution:null}
      : path==='/api/users/workspace/' ? {available:false,workspace:null,role:null,courses:[],members:[],invites:[],usage:[]}
      : path==='/api/notes/references/' ? {note_ids:[]}
      : path==='/api/ai/bots/' ? [{id:1,name:'小宇',bot_type:'planner',is_active:true}]
      : [];
    return route.fulfill({json:data});
  });
  await web.route('**/media/**', route=>route.fulfill({contentType:'image/gif',body:Buffer.from('R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==','base64')}));
  const webPage = await web.newPage();
  webPage.on('pageerror',error=>errors.push(error.message));
  webPage.on('console',message=>{if(message.type()==='error' && !message.text().includes('401')) errors.push(message.text());});
  await webPage.goto(`${base}/login`);
  await webPage.getByLabel('邮箱',{exact:true}).fill('test@example.org');
  await webPage.getByLabel('密码',{exact:true}).fill('test-password');
  await webPage.getByRole('button',{name:'登录',exact:true}).click();
  await webPage.waitForFunction(()=>JSON.parse(localStorage.getItem('auth-storage')||'{}').state?.user?.id===12);
  assert.deepEqual(await webPage.evaluate(()=>Object.keys(JSON.parse(localStorage.getItem('auth-storage')).state)),['user']);
  assert.ok((await webPage.evaluate(()=>window.__webXhr)).every(Boolean),'Web retains credentials mode');
  assert.equal(webRequests.find(r=>r.path==='/api/users/login/').headers['x-csrftoken'],'web-csrf');
  assert.ok(webRequests.every(r=>!r.headers.authorization),'Web uses cookie auth');
  await web.close();
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({pass:true, checks:['delayed Preferences hydration','Authorization and omitted cookies/CSRF','SSE fetch Authorization and credentials omit','WS ticket','protected media ticket','real MP4 playback and 240-second ticket renewal preserve playback','password token rotation and restart','user-only localStorage','Web login keeps Cookie+CSRF and never persists token','health check','server switch logout','Android back closes modal and double-back exits'],requests:requests.length, errors}));
} catch(error) { console.log('BROWSER STATE', await page.locator('body').innerText()); console.log('ERRORS', errors); console.log('RECENT REQUESTS', requests.slice(-15)); const artifactDir = path.resolve('releases/test-artifacts'); mkdirSync(artifactDir,{recursive:true}); await page.screenshot({path:path.join(artifactDir,'native-auth-failure.png')}); throw error; } finally {await browser.close();}
