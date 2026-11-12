// Run against an isolated server with test@astanait.edu.kz / test-password.
// Requires jsdom (NODE_PATH can point to an external installation).
const {JSDOM, VirtualConsole} = require('jsdom');
const assert = require('node:assert/strict');
const base = process.env.PARKGO_TEST_URL || 'http://127.0.0.1:5055';
(async () => {
 const loginPage = await fetch(base+'/login');
 const loginHtml = await loginPage.text();
 const initialCookie = loginPage.headers.get('set-cookie').split(';')[0];
 const loginToken = loginHtml.match(/name="csrf_token" value="([^"]+)"/)[1];
  const login = await fetch(base + '/login', {method:'POST', redirect:'manual', headers:{cookie:initialCookie},
    body:new URLSearchParams({csrf_token:loginToken,email:'test@astanait.edu.kz', password:'test-password'})});
  assert.equal(login.status,302);
  let cookie = login.headers.get('set-cookie').split(';')[0];
  const homePage = await fetch(base+'/', {headers:{cookie}});
  if(homePage.headers.get('set-cookie'))cookie=homePage.headers.get('set-cookie').split(';')[0];
  const homeHtml = await homePage.text();
  const csrfToken = homeHtml.match(/const CSRF_TOKEN="([^"]+)"/)[1];
  const api = (url, options={}) => fetch(new URL(url,base), {...options,
    headers:{'X-CSRF-Token':csrfToken,...options.headers,cookie}});
  const setStatus = async (id,status) => {
    const r = await api('/api/sensor',{method:'POST',headers:{'Content-Type':'application/json','X-Sensor-Token':'parkgo-sensor-demo'},body:JSON.stringify({spot_id:id,status})});
    assert.equal(r.status,200);
  };
  for (const b of await (await api('/api/reservations')).json()) await api('/cancel/'+b.id,{method:'POST'});
  const spots = await (await api('/api/spots')).json();
  const north = spots.filter(s=>s.loc==='Campus North');
  for (const s of north) await setStatus(s.id,'Available');
  const errors=[];
  const vc = new VirtualConsole(); vc.on('jsdomError',e=>errors.push(e.message));
  const dom = new JSDOM(await (await api('/')).text(),{url:base,runScripts:'dangerously',pretendToBeVisual:true,virtualConsole:vc,
    beforeParse(w) {w.fetch=(url,opts={})=>url==='/api/exchange-rate'
      ? Promise.resolve({ok:true,json:async()=>({kzt_per_usd:500,date:'09.11.2026'})})
      : api(url,{...opts,...(opts.body?{body:String(opts.body),headers:{...opts.headers,'Content-Type':'application/x-www-form-urlencoded'}}:{})});}});
  try {
    const $=s=>dom.window.document.querySelector(s);
    const next=()=>new Promise(r=>setTimeout(r,10));
    $('#peek').click(); $('#sbook').click();
    assert($('#spaces')?.classList.contains('on'),'Book must open the parking diagram before the form');
    assert($('#selectSpot').disabled,'Booking requires an explicit spot selection');
    $(`[data-spot="${north[1].id}"]`).click();
    assert.equal($('#selectedSpotName').textContent,'Место A02');
    assert.equal($(`[data-spot="${north[1].id}"]`).getAttribute('aria-pressed'),'true');
    $('#selectSpot').click();
    assert.equal($('#rspot').textContent,'A02');
    $('#cname').value='Selection Test'; $('#plate').value='222 TEST';
    await $('#confirm').onclick();
    assert($('#done').classList.contains('on'));
    const bookings=await (await api('/api/reservations')).json();
    assert.equal(bookings[0].spot,'A02','The backend must reserve the selected spot, not the first free spot');
    await $('#cancel').onclick();
    $('#bookings [data-go="home"]').click(); $('#peek').click(); $('#sbook').click();
    await setStatus(north[0].id,'Occupied'); await dom.window.poll();
    assert($(`[data-spot="${north[0].id}"]`).disabled,'Occupied spots cannot be selected');
    $(`[data-spot="${north[1].id}"]`).click(); $('#selectSpot').click();
    await setStatus(north[1].id,'Occupied'); await dom.window.poll();
    $('#plate').value='333 TEST'; await $('#confirm').onclick();
    assert.equal((await (await api('/api/reservations')).json()).length,0,'Never switch to a different free spot when the selected spot is taken');
    assert($('#confirm').disabled,'A lost selection must disable confirmation');
    $('#bback').click();
    assert($('#spaces').classList.contains('on'));
    assert($('#selectSpot').disabled);
    for(const s of north) await setStatus(s.id,'Available');
    await dom.window.poll();
    $(`[data-spot="${north[1].id}"]`).click(); $('#selectSpot').click();
    await setStatus(north[1].id,'Occupied');
    await $('#confirm').onclick();
    assert.equal((await (await api('/api/reservations')).json()).length,0,'A server conflict between polls must not reserve a different spot');
    assert($('#confirm').disabled);
    $('#bback').click();
    $('#spaces [data-l="en"]').click(); await next();
    assert($('#spaces').textContent.includes('Choose a parking spot'));
    assert.equal(errors.length,0,errors.join('\n'));
    console.log('PASS: explicit selection, exact reserved spot, occupied bays, live conflicts, server conflict between polls, disabled confirmation, return to diagram, RU/EN.');
  } finally {
    dom.window.close();
    for(const s of north) await setStatus(s.id,'Available');
  }
})().catch(e=>{console.error(e);process.exit(1)});
