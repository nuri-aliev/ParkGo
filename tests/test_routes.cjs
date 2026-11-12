// Real browser + real 2GIS integration. Start tests/ui_server.py first.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const base = process.env.PARKGO_TEST_URL || 'http://127.0.0.1:5055';
(async()=>{
 const browser=await chromium.launch({headless:true,
  ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH?{executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH}:{}),
  args:['--no-sandbox','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
 try{
  const context=await browser.newContext({viewport:{width:1440,height:900},permissions:['geolocation'],geolocation:{longitude:71.43,latitude:51.13}});
  const page=await context.newPage(),errors=[];let routeResponses=0;
  page.on('pageerror',e=>errors.push(e.message));
  page.on('response',r=>{if(r.url().includes('routing.api.2gis')&&r.status()===200)routeResponses++});
  await page.request.post(base+'/login',{form:{email:'test@astanait.edu.kz',password:'test-password'}});
  for(const b of await(await page.request.get(base+'/api/reservations')).json())await page.request.post(base+'/cancel/'+b.id);
  await page.goto(base);await page.locator('#loader').waitFor({state:'hidden'});
  await page.waitForFunction(()=>gmap&&Object.values(COORD).every(p=>gmap.getBounds().containsPoint(p)),null,{timeout:15000});
  await page.locator('#peek').click();await page.locator('#sbook').click();
  const bay=page.locator('.parking-bay:not(:disabled)').last();const name=await bay.locator('b').textContent();await bay.click();
  assert(await page.evaluate(()=>document.body.scrollWidth<=innerWidth));
  await page.locator('#spacesRoute').click();
  await page.waitForFunction(()=>!document.querySelector('#locateRoute').disabled,null,{timeout:15000});
  await page.locator('#locateRoute').click();
  await page.waitForFunction(()=>/маршрут построен|Не удалось/.test(document.querySelector('#routeStatus').textContent),null,{timeout:35000});
  assert.match(await page.locator('#routeStatus').textContent(),/маршрут построен/);
  assert(routeResponses>=1,'A real 2GIS routing request must succeed');
  assert(await page.evaluate(()=>gmap.getBounds().containsPoint([71.43,51.13])),'The full route including a distant origin must be visible');
  const cdp=await browser.newBrowserCDPSession();
  const {browserContextIds}=await cdp.send('Target.getBrowserContexts');
  await cdp.send('Browser.setPermission',{permission:{name:'geolocation'},setting:'denied',origin:base,browserContextId:browserContextIds[0]});
  await page.locator('#locateRoute').click();
  await page.waitForFunction(()=>document.querySelector('#routeStatus').textContent.includes('Не удалось определить'),null,{timeout:15000});
  await page.locator('#pickRoute').click();
  await page.locator('#gl').click({position:{x:720,y:480}});
  await page.waitForFunction(()=>/маршрут построен|Не удалось построить/.test(document.querySelector('#routeStatus').textContent),null,{timeout:35000});
  assert.match(await page.locator('#routeStatus').textContent(),/маршрут построен/);
  assert(routeResponses>=2,'Choosing an origin on the map must build another real route');
  await page.locator('#closeRoute').click();
  assert(await page.locator('#spaces').evaluate(e=>e.classList.contains('on')));
  assert.equal(await page.locator('#selectedSpotName').textContent(),'Место '+name);
  await page.setViewportSize({width:390,height:844});
  assert(await page.evaluate(()=>document.body.scrollWidth<=innerWidth));
  await page.locator('#selectSpot').click();assert.equal(await page.locator('#rspot').textContent(),name);
  await page.locator('#plate').fill('444 ROUTE');await page.locator('#confirm').click();
  await page.locator('#done.on').waitFor();await page.locator('#go').click();
  await page.locator('#closeRoute').click();
  assert(await page.locator('#done').evaluate(e=>e.classList.contains('on')));
  await page.locator('#cancel').click();await page.locator('#bookings.on').waitFor();
  assert.deepEqual(errors,[]);
  console.log('PASS: real 2GIS routes from geolocation and map click, denied location fallback, desktop/mobile, selection preserved, return to booking.');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
