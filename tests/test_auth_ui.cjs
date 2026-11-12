// Requires jsdom and an isolated tests/ui_server.py --admin-user (verified mode, no SMTP).
const {JSDOM, VirtualConsole}=require('jsdom');
const assert=require('node:assert/strict');
const base=process.env.PARKGO_TEST_URL||'http://127.0.0.1:5055';
(async()=>{
 const errors=[];
 const load=(html,{storage='blocked',fetch}={})=>{
  const vc=new VirtualConsole();vc.on('jsdomError',e=>errors.push(e.message));
  return new JSDOM(html,{url:base,runScripts:'dangerously',virtualConsole:vc,beforeParse(w){
   w.scrollTo=()=>{};w.HTMLElement.prototype.scrollIntoView=()=>{};
   if(storage==='blocked')for(const kind of ['localStorage','sessionStorage'])Object.defineProperty(w,kind,{get(){throw new w.DOMException('Blocked','SecurityError')}});
   else w.localStorage.setItem('pg-lang',storage);
   if(fetch)w.fetch=(...args)=>fetch(w,...args);
  }});
 };
 const login=await fetch(base+'/login');const html=await login.text();
 const cookie=login.headers.get('set-cookie').split(';')[0];
 const csrf=html.match(/name="csrf_token" value="([^"]+)"/)[1];
 for(const storage of ['blocked','corrupt-language']){
  const dom=load(html,{storage}),d=dom.window.document;
  assert.equal(d.querySelector('#h').textContent,'Вход в ParkGo');
  d.querySelector('#b2').click();assert.equal(d.querySelector('#h').textContent,'Регистрация в ParkGo');
  d.querySelector('[data-l=en]').click();assert.equal(d.querySelector('#h').textContent,'Create a ParkGo account');
  dom.window.close();
 }
 const failed=await fetch(base+'/register',{method:'POST',headers:{cookie},body:new URLSearchParams({csrf_token:csrf,email:'ui@astanait.edu.kz',full_name:'UI Test',password:'test-password'})});
 assert.equal(failed.status,503);
 const dom=load(await failed.text()),d=dom.window.document;
 assert.match(d.querySelector('#authMessage').textContent,/Отправка писем не настроена/);
 assert.equal(d.querySelector('#e2').value,'ui@astanait.edu.kz');assert.equal(d.querySelector('#n2').value,'UI Test');assert.equal(d.querySelector('#p2').value,'');
 d.querySelector('[data-l=en]').click();assert.match(d.querySelector('#authMessage').textContent,/not configured/);
 d.querySelector('#b1').click();assert(d.querySelector('#authMessage').hidden);dom.window.close();
 const authenticated=await fetch(base+'/login',{method:'POST',redirect:'manual',headers:{cookie},body:new URLSearchParams({csrf_token:csrf,email:'test-admin@astanait.edu.kz',password:'test-password'})});
 assert.equal(authenticated.status,302);let adminCookie=authenticated.headers.get('set-cookie').split(';')[0];
 const adminPage=await fetch(base+'/admin',{headers:{cookie:adminCookie}});
 if(adminPage.headers.get('set-cookie'))adminCookie=adminPage.headers.get('set-cookie').split(';')[0];
 let adminHtml=await adminPage.text();
 const token=adminHtml.match(/const CSRF_TOKEN="([^"]+)"/)[1];
 assert.equal((await fetch(base+'/support',{method:'POST',headers:{cookie:adminCookie,'X-CSRF-Token':token},body:new URLSearchParams({message:'UI report'})})).status,200);
 adminHtml=await(await fetch(base+'/admin',{headers:{cookie:adminCookie}})).text();
 for(const failure of ['network','forbidden']){
  const admin=load(adminHtml,{fetch:async w=>{if(failure==='network')throw new w.TypeError('Network error');return {ok:false,status:403}}});
  const ad=admin.window.document;ad.querySelector('[data-p=sup]').click();assert(ad.querySelector('#sup').classList.contains('on'));
  const button=ad.querySelector('[data-resolve]');button.click();await new Promise(resolve=>setTimeout(resolve,10));
  assert(!ad.querySelector('#adminActionError').hidden);assert(!button.disabled);
  assert.match(ad.querySelector('#adminActionError').textContent,failure==='network'?/Cannot reach/:/session expired/);
  admin.window.close();
 }
 assert.deepEqual(errors,[]);
 console.log('PASS: blocked storage, corrupt language, RU/EN errors, retained registration fields, admin tabs and visible request failures.');
})().catch(e=>{console.error(e);process.exit(1)});
