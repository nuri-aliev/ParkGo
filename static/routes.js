// Uses the existing 2GIS map. Location access is requested only on button press.
let routeDestination=null,routeReturn="home",routePicking=false,routeRevision=0;
let directions=null,directionsLoading=null,routeOriginMarker=null;
function loadDirections(){
 if(globalThis.mapgl?.Directions)return Promise.resolve();
 if(directionsLoading)return directionsLoading;
 directionsLoading=new Promise((resolve,reject)=>{
  const script=document.createElement("script");
  script.src="https://unpkg.com/@2gis/mapgl-directions@2/dist/directions.js";
  const timeout=setTimeout(()=>{script.remove();reject(new Error("Directions timeout"))},12000);
  script.onload=()=>{clearTimeout(timeout);globalThis.mapgl?.Directions?resolve():reject(new Error("Directions unavailable"))};
  script.onerror=()=>{clearTimeout(timeout);script.remove();reject(new Error("Directions unavailable"))};
  document.head.append(script);
 }).catch(error=>{directionsLoading=null;throw error});
 return directionsLoading;
}
function routeMessage(key){$("#routeStatus").textContent=t(key)}
function fitRoute(route,origin,destination){
 const bounds=new mapgl.LngLatBoundsClass({southWest:origin,northEast:origin});bounds.extend(destination);
 const sections=[route.begin_pedestrian_path?.geometry,
  ...(route.maneuvers||[]).flatMap(m=>m.outcoming_path?.geometry||[]),route.end_pedestrian_path?.geometry];
 for(const section of sections){
  // Routing API returns geometry.selection as WKT LINESTRING(lon lat, ...).
  for(const match of (section?.selection||"").matchAll(/(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)/g))bounds.extend([Number(match[1]),Number(match[2])]);
 }
 const panel=$("#routePanel"),wide=gmap.getContainer().clientWidth>=700;
 gmap.fitBounds(bounds,{maxZoom:17,padding:wide?{left:panel.offsetWidth+48,right:48,top:48,bottom:48}:{left:32,right:32,top:panel.offsetHeight+40,bottom:48},animation:{duration:0}});
}
async function startRoute(l){
 const revision=++routeRevision;
 routeReturn=$(".scr.on")?.id||"home";routeDestination=l;routePicking=false;
 show("home");$("#app").classList.add("route-view");$("#routePanel").hidden=false;render();
 window.ParkGoMotion?.reveal($("#routePanel"));
 $("#routeDestination").textContent=lotName(l);$("#routeExternal").href=navUrl(l);
 $("#locateRoute").disabled=true;$("#pickRoute").disabled=true;routeMessage("loading");
 await mapReady;
 if(revision!==routeRevision)return;
 if(!gmap||!COORD[l]){routeMessage("routeMapError");return}
 gmap.invalidateSize();gmap.setCenter(COORD[l]);gmap.setZoom(15);
 $("#locateRoute").disabled=false;$("#pickRoute").disabled=false;routeMessage("routeChoose");
}
async function buildRoute(origin,revision){
 if(revision!==routeRevision||!routeDestination||!gmap)return;
 routePicking=false;routeMessage("routeLoading");
 $("#locateRoute").disabled=true;$("#pickRoute").disabled=true;
 try{
  await loadDirections();
  if(revision!==routeRevision)return;
  directions?.clear();
  const currentDirections=new mapgl.Directions(gmap,{directionsApiKey:KEY});directions=currentDirections;
  let routes=[];currentDirections.once("directionsLoaded",event=>{routes=event.routes});
  routeOriginMarker?.destroy();
  routeOriginMarker=new mapgl.Marker(gmap,{coordinates:origin});
  await currentDirections.carRoute({points:[origin,COORD[routeDestination]]});
  if(revision!==routeRevision){currentDirections.clear();return}
  if(!routes.length)throw new Error("No route found");
  fitRoute(routes[0],origin,COORD[routeDestination]);
  if(revision===routeRevision)routeMessage("routeReady");
 }catch{if(revision===routeRevision)routeMessage("routeError")}
 finally{if(revision===routeRevision){$("#locateRoute").disabled=false;$("#pickRoute").disabled=false}}
}
function handleRouteMapClick(coordinates){
 if(routePicking&&routeDestination)buildRoute(coordinates,++routeRevision);
}
$("#pickRoute").onclick=()=>{++routeRevision;routePicking=true;directions?.clear();routeOriginMarker?.destroy();routeOriginMarker=null;$("#locateRoute").disabled=false;routeMessage("routeClick")};
$("#locateRoute").onclick=()=>{
 const revision=++routeRevision;routePicking=false;
 if(!navigator.geolocation){routeMessage("routeGeoError");return}
 routeMessage("routeLocating");$("#locateRoute").disabled=true;
 navigator.geolocation.getCurrentPosition(position=>{
  if(revision===routeRevision)buildRoute([position.coords.longitude,position.coords.latitude],revision);
 },()=>{if(revision===routeRevision){routeMessage("routeGeoError");$("#locateRoute").disabled=false}},
 {enableHighAccuracy:true,timeout:12000,maximumAge:30000});
};
$("#closeRoute").onclick=()=>{
 ++routeRevision;routePicking=false;routeDestination=null;directions?.clear();
 routeOriginMarker?.destroy();routeOriginMarker=null;
 $("#routePanel").hidden=true;$("#app").classList.remove("route-view");
 render();
 if(routeReturn==="done"&&BOOKINGS.some(b=>b.id===rid))openBooking(rid);
 else show(routeReturn==="done"?"bookings":routeReturn);
 requestAnimationFrame(()=>gmap?.invalidateSize());
};
