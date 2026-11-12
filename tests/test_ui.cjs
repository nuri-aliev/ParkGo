// npm install jsdom; start an isolated test server with test@astanait.edu.kz / test-password.
const {JSDOM,VirtualConsole}=require('jsdom');
const assert=require('node:assert/strict');
const base=process.env.PARKGO_TEST_URL||'http://127.0.0.1:5055';
(async()=>{
 const loginPage = await fetch(base+'/login');
 const loginHtml = await loginPage.text();
 const initialCookie = loginPage.headers.get('set-cookie').split(';')[0];
 const loginToken = loginHtml.match(/name="csrf_token" value="([^"]+)"/)[1];
 const login=await fetch(base+'/login',{method:'POST',redirect:'manual',headers:{cookie:initialCookie},body:new URLSearchParams({csrf_token:loginToken,email:'test@astanait.edu.kz',password:'test-password'})});
 let cookie=login.headers.get('set-cookie').split(';')[0];
 let dom;const errors=[];const saved={};
 const load=async()=>{
  if(dom){Object.assign(saved,Object.fromEntries(Object.entries(dom.window.localStorage)));dom.window.close()}
  const page=await fetch(base,{headers:{cookie}});
  if(page.headers.get('set-cookie'))cookie=page.headers.get('set-cookie').split(';')[0];
  const html=await page.text();
  const vc=new VirtualConsole();vc.on('jsdomError',e=>errors.push(e.message));
  dom=new JSDOM(html,{url:base,runScripts:'dangerously',pretendToBeVisual:true,virtualConsole:vc,beforeParse(w){
   for(const[k,v]of Object.entries(saved))w.localStorage.setItem(k,v);
   w.fetch=(url,opts={})=>url==='/api/exchange-rate'?Promise.resolve({ok:true,json:async()=>({kzt_per_usd:500,date:'05.11.2026'})}):fetch(new URL(url,base),{...opts,headers:{...opts.headers,cookie},body:opts.body?String(opts.body):undefined,...(opts.body?{headers:{...opts.headers,cookie,'Content-Type':'application/x-www-form-urlencoded'}}:{})});
  }});
 };
 const $=s=>dom.window.document.querySelector(s);
 const until=async fn=>{for(let i=0;i<100;i++){if(fn())return;await new Promise(r=>setTimeout(r,60))}throw Error('Condition timeout')};
 await load();assert(!$('a.adm'));await until(()=>$('#loader').hidden);
 async function book(car){$('#peek').click();$('#sbook').click();dom.window.document.querySelector('.parking-bay:not(:disabled)').click();$('#selectSpot').click();$('#cname').value='Test';$('#plate').value=car;await $('#confirm').onclick();assert($('#done').classList.contains('on'))}
 await book('111 AAA');const ref=$('#dref').textContent;
 await load();assert($('#done').classList.contains('on'));assert.equal($('#dref').textContent,ref);
 $('#done [data-go=home]').click();await book('222 BBB');
 $('#done [data-go=bookings]').click();await until(()=>dom.window.document.querySelectorAll('.booking-item').length===2);
 assert.equal($('#bookings .nav [data-go=bookings]').getAttribute('aria-current'),'page');
 $('#bookings .nav [data-go=support]').click();assert($('#support').classList.contains('on'));
 $('#support .nav [data-go=bookings]').click();await until(()=>dom.window.document.querySelectorAll('.booking-item').length===2);
 $('.booking-item').click();await $('#cancel').onclick();assert.equal(dom.window.document.querySelectorAll('.booking-item').length,1);
 $('#bookings [data-l=en]').click();$('#bookings [data-go=home]').click();$('#peek').click();assert($('#sheet').textContent.includes('$1.00'));
 assert.equal(errors.length,0,errors.join('\n'));
 console.log('PASS: navigation, second car, reload, saved bookings, cancellation, hidden admin link, English USD, loader timeout, no JS errors (jsdom).');dom.window.close();
})().catch(e=>{console.error(e);process.exit(1)});
