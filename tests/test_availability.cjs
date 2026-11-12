// Regression: delayed snapshots must not overwrite newer availability.
const {JSDOM,VirtualConsole}=require('jsdom');
const assert=require('node:assert/strict');
const base=process.env.PARKGO_TEST_URL||'http://127.0.0.1:5055';
(async()=>{
 const queue=[],errors=[],vc=new VirtualConsole();vc.on('jsdomError',e=>errors.push(e.message));
 const html=await(await fetch(base)).text();
 const dom=new JSDOM(html,{url:base,runScripts:'dangerously',pretendToBeVisual:true,virtualConsole:vc,
  beforeParse(w){w.setInterval=()=>0;w.fetch=url=>url==='/api/spots'?new Promise(resolve=>queue.push(resolve)):Promise.resolve({ok:false})}});
 try{
  const w=dom.window,$=s=>w.document.querySelector(s);
  w.openSpaces('Campus North');
  const initial=w.eval('SPOTS.map(s=>({...s}))'),north=initial.filter(s=>s.loc==='Campus North');
  assert.equal(north.length,2,'Use the default isolated fixture');
  const occupied=initial.map(s=>s.id===north[0].id?{...s,status:'Occupied',free:false}:s);
  const older=w.poll(),newer=w.poll();
  const resolveOlder=queue.shift(),resolveNewer=queue.shift();
  // Hold the old snapshot until after the new response has been displayed.
  resolveNewer({ok:true,json:async()=>occupied});await newer;
  assert($(`[data-spot="${north[0].id}"]`).disabled);
  const currentCount=$('#spacesCount').textContent;
  resolveOlder({ok:true,json:async()=>initial});await older;
  assert($(`[data-spot="${north[0].id}"]`).disabled,'A delayed older response must not make an occupied bay available again');
  assert.equal($('#spacesCount').textContent,currentCount,'The count must retain the latest snapshot');
  $(`[data-spot="${north[1].id}"]`).click();
  assert.equal($('#spacesCount').textContent,currentCount,'Selecting a place does not reserve it or reduce availability');
  assert.match($(`[data-spot="${north[1].id}"] .bay-state`).textContent,/Выбрано.*свободно/);
  const reserved=occupied.map(s=>s.id===north[1].id?{...s,status:'Reserved',free:false}:s);
  const pending=w.poll();queue.shift()({ok:true,json:async()=>reserved});await pending;
  assert.equal(w.document.querySelectorAll('.parking-bay:not(:disabled)').length,0);
  assert.match($('#spacesCount').textContent,/0.*2/);
  assert.match($('#spacesBreakdown').textContent,/Занято: 1.*Забронировано: 1/);
  assert($(`[data-spot="${north[0].id}"] img`),'Occupied bays display a car');
  assert(!$(`[data-spot="${north[1].id}"] img`),'A reservation must not pretend that a physical car is present');
  assert.match($(`[data-spot="${north[1].id}"] .bay-state`).textContent,/Бронь/);
  assert($('#selectSpot').disabled);
  assert.equal(errors.length,0,errors.join('\n'));
  console.log('PASS: late response ignored, count matches bays, selected stays available, occupied and reserved are distinct.');
 }finally{dom.window.close()}
})().catch(e=>{console.error(e);process.exit(1)});
