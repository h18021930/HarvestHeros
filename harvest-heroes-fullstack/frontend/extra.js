'use strict';
/* Harvest Heroes: connected features layered onto the original pixel-battle engine.
   All player progress is persisted via the Python API, never trusted from browser battle results. */
const HH = {
  token: localStorage.getItem('harvest-heroes-token') || '',
  farms: [], plans: [], plantings: [], crops: {}, map: null, marker: null,
  coords: {lat: null, lon: null}, battleId: null, ready: false,
};

async function hhApi(path, options = {}) {
  const headers = {...(options.body ? {'Content-Type':'application/json'} : {}), ...(HH.token ? {'Authorization':'Bearer '+HH.token} : {})};
  const response = await fetch('/api'+path, {...options, headers: {...headers, ...(options.headers || {})}});
  let data;
  try { data = await response.json(); } catch { data = {}; }
  if (!response.ok) {
    const detail = typeof data.detail === 'string' ? data.detail : 'HTTP '+response.status;
    throw new Error(detail);
  }
  return data;
}
function hhStatus(message, isError=false) {
  const el = $('#sync'); el.textContent = message; el.style.color = isError ? '#ff9f9f' : '#a8ebb3';
}
function hhError(err) { hhStatus(err.message || 'Connection error', true); console.error('Harvest Heroes:',err); }
async function hhPlayer() {
  try {
    if (!HH.token) {
      const data = await hhApi('/players', {method:'POST', body: JSON.stringify({name:'Farmer'})});
      HH.token = data.token;
      localStorage.setItem('harvest-heroes-token', HH.token);
    }
    const me = await hhApi('/me');
    S.xp = me.xp; S.w = me.wins; stat(); HH.ready = true;
    hhStatus('PROGRESS SAVED');
  } catch (err) { HH.ready=false; hhError(err); throw err; }
}
async function hhRefresh() {
  const [me, farms, plans, plants] = await Promise.all([
    hhApi('/me'), hhApi('/farms'), hhApi('/plans'), hhApi('/plantings')
  ]);
  HH.farms = farms; HH.plans = plans; HH.plantings = plants;
  S.xp = me.xp; S.w = me.wins;
  S.st = {}; S.def = {};
  const byId = Object.fromEntries(farms.map(f=>[f.id,f]));
  S.log = plans.slice(0,10).map(entry=>{
    const p=entry.content, f=byId[entry.farm_id];
    if(f) S.st[f.biome]=1;
    S.def[p.threat]=(S.def[p.threat]||0)+1;
    return {m:p.threat,c:p.crop,l:p.location,d:entry.created_at.slice(0,10)};
  });
  stat();
  return {farms, plans, plants};
}
function hhToday() { return new Date().toLocaleDateString('en-CA'); }
function hhFarmPayload() {
  const lat=HH.coords.lat, lon=HH.coords.lon;
  return {
    name: (P.crop||'Crop')+' farm',country:P.country,region:$('#region').value.trim(),crop:P.crop,
    biome:P.biome,soil:P.soil,season:P.season,size:P.size,water:P.water,
    lat:lat===null?null:lat,lon:lon===null?null:lon
  };
}
const hhOriginalShow = show;
show = function(id) {
  hhOriginalShow(id);
  ['atlas','cards','tracker','rotation','saved','dashboard','instructions'].forEach(name=>$('#'+name).hidden=name!==id);
  if(id==='dashboard') hhDashboard().catch(hhError);
  if(id==='atlas') hhAtlas();
  if(id==='cards') hhCards();
  if(id==='tracker') hhTracker().catch(hhError);
  if(id==='rotation') hhRotation();
  if(id==='saved') hhSaved().catch(hhError);
  if(id==='journal') hhRefresh().then(()=>drawJournal()).catch(hhError);
  if(id==='map') hhRefresh().then(()=>drawMap()).catch(hhError);
};
document.querySelectorAll('[data-go]').forEach(btn=>btn.onclick=()=>show(btn.dataset.go));

/* A live-location pin is optional; NASA POWER data is explicitly historical. */
function hhSetCoords(lat, lon) {
  lat=Number(lat);lon=Number(lon);
  if(!Number.isFinite(lat)||!Number.isFinite(lon)||lat < -90||lat > 90||lon < -180||lon > 180) throw new Error('Coordinates must be valid latitude/longitude values');
  HH.coords={lat,lon};
  $('#lat').value=lat.toFixed(5);$('#lon').value=lon.toFixed(5);
  $('#selected-loc').firstChild.textContent='Location pin: '+lat.toFixed(3)+', '+lon.toFixed(3)+' — ';
  if(HH.map && window.L) {
    if(!HH.marker) HH.marker=L.marker([lat,lon]).addTo(HH.map);
    else HH.marker.setLatLng([lat,lon]);
    HH.map.panTo([lat,lon]);
  }
}
function hhAtlas() {
  $('#atlas-biomes').innerHTML=Object.entries(BIO).map(([k,v])=>`<button data-atlas-biome="${k}">${esc(v.n)} ${S.st[k]?'★':''}</button>`).join('');
  document.querySelectorAll('[data-atlas-biome]').forEach(b=>b.onclick=()=>{$('#biome').value=b.dataset.atlasBiome;show('start')});
  if(!HH.map && window.L) {
    HH.map=L.map('leaflet-map',{worldCopyJump:true}).setView([20,0],2);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:18,attribution:'&copy; OpenStreetMap contributors'}).addTo(HH.map);
    HH.map.on('click',e=>hhSetCoords(e.latlng.lat,e.latlng.lng));
    if(HH.coords.lat!==null) hhSetCoords(HH.coords.lat,HH.coords.lon);
  }
  if(HH.map) setTimeout(()=>HH.map.invalidateSize(),50);
}
$('#apply-pin').onclick=()=>{try{if($('#lat').value===''||$('#lon').value==='')throw new Error('Enter both coordinates');hhSetCoords($('#lat').value,$('#lon').value);show('start')}catch(e){hhError(e)}};
$('#use-location').onclick=()=>{
  if(!navigator.geolocation){hhStatus('Geolocation is unavailable; enter coordinates manually',true);return;}
  navigator.geolocation.getCurrentPosition(p=>{hhSetCoords(p.coords.latitude,p.coords.longitude);hhStatus('Location pin selected')},()=>hhStatus('Location permission denied; coordinates can be entered manually',true),{enableHighAccuracy:false,timeout:10000});
};
$('#nasa').onclick=async()=>{
  const el=$('#nasa-result');
  try{
    if($('#lat').value===''||$('#lon').value==='')throw new Error('Choose a map pin first');
    hhSetCoords($('#lat').value,$('#lon').value);
    el.textContent='Retrieving NASA POWER historical observations…';
    await hhPlayer();
    const d=await hhApi(`/environment?lat=${encodeURIComponent(HH.coords.lat)}&lon=${encodeURIComponent(HH.coords.lon)}`);
    el.innerHTML=`<p><b>NASA POWER historical estimates (${esc(d.start)} to ${esc(d.end)})</b></p><p>Mean air temperature: <b>${d.average_temperature_c} °C</b> · Cumulative precipitation: <b>${d.total_precipitation_mm} mm</b> · Valid temperature days: ${d.sample_count}</p><small>${esc(d.note)}</small>`;
  }catch(e){el.textContent=e.message;hhError(e)}
};

/* Override the browser-trusting original game flow with authoritative battle turns. */
startBattle = async function() {
  try {
    await hhPlayer();hhStatus('STARTING BATTLE…');
    const data=await hhApi('/battles/start',{method:'POST',body:JSON.stringify({farm:hhFarmPayload()})});
    const M=MON[data.threat];
    HH.battleId=data.id;
    B={id:data.id,k:data.threat,why:data.why,eh:data.eh,ph:data.ph,pp:data.pp,good:0,turn:0,busy:1,sh:{e:0,p:0},dead:0,pdead:0,fx:null};
    $('#en').textContent=M.name;$('#et').textContent=M.type;bars();moves();show('battle');
    await say(`You arrive in ${P.loc} to grow ${P.crop}. A wild ${M.name} appeared!`);
    await say(M.intro);B.busy=0;moves();$('#txt').textContent='What will FARMER do? Pick the move that best counters '+M.type+'.';
    hhStatus('BATTLE SAVED');
  }catch(e){hhError(e);$('#hint').textContent='Unable to start battle: '+e.message;show('start')}
};
turn = async function(k) {
  if(!B || B.busy)return;
  B.busy=1;moves();const M=MON[B.k];
  try {
    await say(`FARMER used ${MV[k].n}!`);
    const data=await hhApi(`/battles/${B.id}/moves`,{method:'POST',body:JSON.stringify({move:k})});
    await fx(true,MV[k].c);B.eh=data.eh;B.pp=data.pp;B.good=data.good;B.sh.e=performance.now()+450;pop(data.damage,1);bars();
    if(data.damage>=30)await say("It's super effective!");
    else if(data.damage<=12)await say('It barely helped...');
    if(data.status==='won'){
      B.dead=performance.now();await say(`${M.name} was defeated!`);
      return hhWin(data.plan,data.player);
    }
    const attack=data.enemy_attack[(data.turn-1)%3];
    await say(`${M.name} used ${attack}!`);
    await fx(false,M.col);B.ph=data.ph;B.turn=data.turn;B.sh.p=performance.now()+450;pop(data.enemy_damage,0);bars();
    if(data.status==='lost'){
      B.pdead=performance.now();await say(B.ph===0?'FARMER is out of energy…':'FARMER has no moves left…');
      return lose();
    }
    B.busy=0;moves();$('#txt').textContent='What will FARMER do?';
  }catch(e){B.busy=0;moves();hhError(e);$('#txt').textContent='Connection error: '+e.message+' — you can retry your move.'}
};
function hhWin(plan,playerData) {
  S.xp=playerData.xp;S.w=playerData.wins;S.def[B.k]=(S.def[B.k]||0)+1;S.st[P.biome]=1;
  S.log.unshift({m:B.k,c:P.crop,l:P.loc,d:new Date().toLocaleDateString()});S.log=S.log.slice(0,10);
  stat();
  TXT=`${plan.title}\nThreat: ${plan.monster}\nWhy: ${plan.why.join(', ')}\n\nActions:\n${plan.actions.map(a=>'- '+a).join('\n')}\n\nSoil: ${plan.soil_guidance}\nCrop: ${plan.crop_guidance}\nRotation: ${plan.rotation.advice}\n\n${plan.disclaimer}`;
  $('#plan').innerHTML=`<h2>🏆 FIELD PLAN UNLOCKED!</h2><p><b>+50 XP</b> | Level ${lvl()} | ${S.w} victories | ${esc(plan.monster)} added to the journal</p>
    <p><b>What caused this challenge?</b> ${esc(plan.why.join(', ')||'Selected farm conditions')}</p>
    <h3>Your farm actions</h3><ul>${plan.actions.map(a=>`<li>${esc(a)}</li>`).join('')}</ul>
    <h3>Soil implications</h3><p>${esc(plan.soil_guidance)}</p>
    <h3>Crop-specific guidance</h3><p>${esc(plan.crop_guidance)}</p>
    <h3>Rotation implications</h3><p>${esc(plan.rotation.advice)}</p>
    <p><small>${esc(plan.disclaimer)}</small></p>
    <div class="row"><button id="cp">COPY PLAN</button><button id="sv">SAVE AS TEXT</button><button id="track-from-plan">TRACK PLANT</button><button data-go="saved">SAVED PLANS</button><button id="again">FARM AGAIN</button></div>`;
  $('#cp').onclick=()=>navigator.clipboard.writeText(TXT).then(()=>$('#cp').textContent='COPIED!',hhError);
  $('#sv').onclick=()=>{const url=URL.createObjectURL(new Blob([TXT],{type:'text/plain'}));const a=document.createElement('a');a.href=url;a.download='field-plan.txt';a.click();setTimeout(()=>URL.revokeObjectURL(url),2000)};
  $('#track-from-plan').onclick=()=>show('tracker');
  $('#again').onclick=()=>show('start');
  $('#plan [data-go]').onclick=()=>show('saved');
  show('plan');hhStatus('VICTORY +50 XP · PLAN SAVED');
  hhRefresh().catch(hhError);
}

/* Original miniature pixel sprites are retained for battle creatures; crop cards get new artwork. */
function hhCropArt(key) {
  const c=document.createElement('canvas');c.width=c.height=32;const g=c.getContext('2d');
  let seed=0;for(let i=0;i<key.length;i++)seed=(seed*31+key.charCodeAt(i))>>>0;
  const paint=(x,y,w,h,color)=>{g.fillStyle=color;g.fillRect(x,y,w,h)};
  const green=['#2a8c48','#378f3d','#429d45','#618c2d'][seed%4];
  const detail=['#e8c847','#c94e39','#d8bd83','#754ec9','#f4dd74'][seed%5];
  paint(12,8,3,21,'#2c6030');paint(19,10,2,19,'#427c37');
  for(let y=11;y<25;y+=5){const left=(seed+y)%3;paint(7-left,y,7+left,3,green);paint(17,y+1,6+left,3,'#58b65b');paint(5,y+2,5,2,'#235b32')}
  if(['potatoes','dates'].includes(key)){
    for(let x=9;x<=21;x+=6){paint(x,25,5,4,detail);paint(x+1,26,2,2,'#e3cf9e')}
  }else if(['corn','wheat','barley','rice'].includes(key)){
    for(let y=3;y<17;y+=4){paint(12,y,6,4,detail);paint(14,y-1,2,3,'#f9e89b')}
  }else if(['tomatoes','soybean'].includes(key)){
    for(const [x,y] of [[7,11],[20,16],[15,6]]){paint(x,y,6,6,detail);paint(x+2,y-1,3,2,green)}
  }else{paint(12,4,8,6,detail);paint(14,2,4,4,green)}
  paint(3,29,26,3,'#775337');paint(6,28,20,2,'#b0804e');
  return c.toDataURL('image/png');
}
async function hhLoadCrops() {
  if(Object.keys(HH.crops).length)return;
  const data=await hhApi('/crops');HH.crops=data.crops;
  const options=Object.entries(HH.crops).map(([key,c])=>`<option value="${key}">${esc(c.name)}</option>`).join('');
  $('#plant-crop').innerHTML=options;$('#rotation-crop').innerHTML=options;
}
async function hhCards() {
  try{await hhLoadCrops();
    $('#crop-cards').innerHTML=Object.entries(HH.crops).map(([key,c])=>`<article class="crop-card"><h3>${esc(c.name)}<small>${esc(c.family)}</small></h3>
    <div class="crop-art"><img alt="Pixel-art illustration of ${esc(c.name)}" src="${hhCropArt(key)}"></div>
    <p class="crop-meta"><strong>GROW TIME</strong> ~${c.days} days · <strong>WATER</strong> ${esc(c.water)}</p>
    <p class="crop-meta"><strong>SOIL</strong> ${esc(c.soil)}</p>
    <p class="crop-meta"><strong>USES</strong> ${esc(c.uses)}</p>
    <p class="fact">🌿 ${esc(c.fact)}</p><p class="fact">${esc(c.note)}</p>
    <button data-card-crop="${key}">GROW THIS CROP</button></article>`).join('');
    document.querySelectorAll('[data-card-crop]').forEach(btn=>btn.onclick=()=>{$('#crop').value=btn.dataset.cardCrop;show('start')});
  }catch(e){hhError(e);$('#crop-cards').textContent='Crop cards could not be loaded: '+e.message}
}

/* Crop dates are simple education estimates; they are never claimed to predict harvests. */
async function hhTracker() {
  await hhPlayer();await hhLoadCrops();await hhRefresh();
  $('#plant-date').value||=hhToday();
  $('#plant-farm').innerHTML=HH.farms.length?HH.farms.map(f=>`<option value="${esc(f.id)}">${esc(f.name)} (${esc(f.country)})</option>`).join(''):'<option value="">No farms yet — finish or start a battle first</option>';
  $('#plant-form button').disabled=!HH.farms.length;
  $('#plantings').innerHTML=HH.plantings.length?HH.plantings.map(row=>{
    const tl=row.timeline;
    return `<article class="plant-panel"><h3>🌿 ${esc(HH.crops[row.crop]?.name || row.crop)}</h3>
      <p>Planted: ${esc(row.planted_on)} · Estimated harvest: <b>${esc(tl.estimated_harvest)}</b> · ${tl.days_remaining} estimated days remaining</p>
      <div class="progress-bar" aria-label="${tl.progress_percent}% estimated progress"><span style="width:${tl.progress_percent}%"></span></div><p>${tl.progress_percent}% of illustrative growing time</p>
      <div class="stages">${tl.stages.map(s=>`<div class="stage ${s.status}"><b>${esc(s.name)}</b><div>${esc(s.start)} – ${esc(s.end)}</div><small>${esc(s.status)}</small></div>`).join('')}</div>
      <form data-event-form="${esc(row.id)}"><select name="kind" aria-label="Task type"><option value="water">Watered</option><option value="fertilise">Fertilised</option><option value="inspect">Inspected</option><option value="pest">Pest check</option><option value="harvest">Harvested</option><option value="note">Other note</option></select><input name="note" maxlength="500" placeholder="Field activity notes"><button>LOG ACTIVITY</button></form>
      <p><small>${esc(tl.disclaimer)}</small></p>
      <ul>${row.events.slice(0,8).map(e=>`<li>${esc(e.event_on)}: ${esc(e.kind)} — ${esc(e.note)}</li>`).join('')||'<li>No activities logged yet.</li>'}</ul></article>`;
  }).join(''):'<div class="box">No crops planted yet. Record your first planting above!</div>';
  document.querySelectorAll('[data-event-form]').forEach(form=>form.onsubmit=async e=>{
    e.preventDefault();const id=form.dataset.eventForm;
    try{await hhApi(`/plantings/${id}/events`,{method:'POST',body:JSON.stringify({kind:form.elements.kind.value,note:form.elements.note.value})});
      $('#tracker-feedback').textContent='Activity saved';await hhTracker();}catch(err){hhError(err);$('#tracker-feedback').textContent=err.message}
  });
}
$('#plant-form').onsubmit=async e=>{
  e.preventDefault();
  try{
    const input={farm_id:$('#plant-farm').value,crop:$('#plant-crop').value,planted_on:$('#plant-date').value,note:$('#plant-note').value};
    await hhApi('/plantings',{method:'POST',body:JSON.stringify(input)});
    $('#tracker-feedback').textContent='Planting recorded. Growth dates are estimates.';
    await hhTracker();
  }catch(err){hhError(err);$('#tracker-feedback').textContent=err.message}
};

async function hhRotation() {try{await hhLoadCrops()}catch(e){hhError(e)}}
$('#rank-climate').onclick=async()=>{
  const el=$('#climate-rotation-results'),btn=$('#rank-climate');
  try{
    if(HH.coords.lat===null || HH.coords.lon===null)throw new Error('Choose a pin in LOCATION MAP first, then return to ROTATION.');
    await hhPlayer();btn.disabled=true;el.textContent='Fetching historical NASA POWER weather and SoilGrids data. External services may be slow…';
    const crop=$('#rotation-crop').value;
    const known={corn:'maize',maize:'maize',wheat:'winter_wheat',soybeans:'soybean',soybean:'soybean'};
    const history=$('#rotation-history').value.split(',').map(x=>x.trim()).filter(Boolean).map(x=>known[x]||x);
    const normalizedRotation=[...(history.length?history:[crop])].slice(0,3).map(x=>known[x]||x);
    const data=await hhApi('/rotations/rank',{method:'POST',body:JSON.stringify({lat:HH.coords.lat,lon:HH.coords.lon,current_rotation:normalizedRotation,top_n:5,sequence_length:3})});
    el.innerHTML=`<b>Historical period:</b> ${esc(data.weather_period.start)}–${esc(data.weather_period.end)}<p>Estimated mean ET0: ${esc(data.mean_et0_mm_day)} mm/day · Soil organic carbon: ${data.soil.soc_g_kg===null?'Unavailable':data.soil.soc_g_kg+' g/kg'} (${esc(data.soil_source)})</p>
      <h3>Top-ranked three-year rotations</h3><ol>${data.top_rotations.map(r=>`<li><b>${esc(r.sequence.join(' → '))}</b> · index ${r.rsi.toFixed(3)}<p>Compared with continuous maize: ${r.impact_metrics.water_saved_mm} mm water difference, ${r.impact_metrics.nitrogen_fertilizer_avoided_kg_ha} kg/ha nitrogen-balance difference, ${r.impact_metrics.bare_field_days_avoided} fewer bare-field days (negative = more).</p><details><summary>Year-by-year implications & uncertainties</summary><ul>${r.year_breakdown.map(y=>`<li>${esc(y.crop)}: ${y.explanation.nitrogen_balance_kg_ha} kg N/ha net balance, ~${y.explanation.water_demand_mm} mm seasonal water demand, ${y.bare_field_days} potential days without living cover</li>`).join('')}</ul><p>${r.risks_and_gaps.map(esc).join(' ')}</p></details></li>`).join('')}</ol>
      ${data.current_rotation?`<p><b>Current rotation index:</b> ${data.current_rotation.rsi.toFixed(3)} (${esc(data.current_rotation.sequence.join(' → '))})</p>`:''}
      <p>${esc(data.note)}</p>`;
  }catch(err){el.textContent=err.message;hhError(err)}finally{btn.disabled=false}
};
$('#rotation-form').onsubmit=async e=>{
  e.preventDefault();const el=$('#rotation-results');
  try{
    const input={crop:$('#rotation-crop').value,history:$('#rotation-history').value.split(',').map(x=>x.trim()).filter(Boolean)};
    const data=await hhApi('/rotation',{method:'POST',body:JSON.stringify(input)});
    el.innerHTML=`<h3>Rotation recommendation</h3><p>Current crop family: <b>${esc(data.family)}</b></p>
      <p>${data.previous_same_family.length?`⚠️ Same-family crops in history: ${esc(data.previous_same_family.join(', '))}`:'No recognized same-family crops entered.'}</p>
      <p>${esc(data.advice)}</p><h3>Other crop families to consider</h3>
      <ul>${data.alternatives.map(c=>`<li>${esc(c.name)} — ${esc(c.family)}</li>`).join('')}</ul>
      <small>Educational options, not a locally validated rotation schedule. Check climate, soil, season and market before planting.</small>`;
  }catch(err){hhError(err);el.textContent=err.message}
};

async function hhSaved() {
  await hhPlayer();await hhRefresh();
  $('#saved-farms').innerHTML=HH.farms.length?HH.farms.map(f=>`<div class="saved-item"><b>${esc(f.name)}</b><p>${esc(f.crop)} · ${esc(f.region||f.country)} · ${esc(BIO[f.biome].n)}</p><button data-saved-farm="${esc(f.id)}">FIGHT HERE AGAIN</button></div>`).join(''):'No farms saved yet.';
  document.querySelectorAll('[data-saved-farm]').forEach(btn=>btn.onclick=()=>{
    const f=HH.farms.find(f=>f.id===btn.dataset.savedFarm);if(!f)return;
    ['country','region','crop','biome','soil','season','size','water'].forEach(field=>$('#'+field).value=f[field]);
    if(f.lat!==null && f.lon!==null)hhSetCoords(f.lat,f.lon);show('start');
  });
  $('#saved-plans').innerHTML=HH.plans.length?HH.plans.map(entry=>{
    const p=entry.content;
    return `<div class="saved-item"><b>${esc(p.title)}</b><p>${esc(p.monster)} defeated · ${esc(entry.created_at.slice(0,10))}</p><details><summary>VIEW FIELD PLAN</summary>
      <ul>${p.actions.map(a=>`<li>${esc(a)}</li>`).join('')}</ul><p>${esc(p.soil_guidance)}</p><p>${esc(p.crop_guidance)}</p><small>${esc(p.disclaimer)}</small></details></div>`;
  }).join(''):'Win a battle to unlock your first saved field plan.';
}
/* Practical farmer workspace. NASA POWER observations are obtained only via backend. */
async function hhDashboard() {
  await hhPlayer();
  await hhRefresh();
  const metrics=$('#dashboard-stats');
  metrics.innerHTML=`<div><strong>${HH.farms.length}</strong><span>Saved fields</span></div><div><strong>${HH.plantings.length}</strong><span>Planting records</span></div><div><strong>${S.w}</strong><span>Game victories</span></div>`;
  const select=$('#dashboard-farm');
  select.innerHTML='<option value="">Choose a saved field with coordinates</option>'+
    HH.farms.filter(f=>f.lat!==null && f.lon!==null).map(f=>`<option value="${esc(f.id)}">${esc(f.name)} — ${esc(f.region||f.country)}</option>`).join('');
  if(!select.options.length || select.options.length===1) $('#dashboard-weather').textContent='Add a map pin to a new field in GAME, or use LOCATION MAP to select coordinates.';
  $('#dashboard-plantings').innerHTML=HH.plantings.length?HH.plantings.slice(0,8).map(p=>
    `<div class="saved-item"><b>${esc(HH.crops[p.crop]?.name||p.crop)}</b> · Planted ${esc(p.planted_on)} · Approximate harvest ${esc(p.timeline.estimated_harvest)}<p>${p.events.length} logged field activities</p></div>`).join(''):'No plantings yet. Open TRACKER to record a crop.';
}
$('#dashboard-nasa').onclick=async()=>{
  const el=$('#dashboard-weather'),btn=$('#dashboard-nasa');
  try {
    await hhPlayer();
    const farm=HH.farms.find(f=>f.id===$('#dashboard-farm').value);
    const coords=farm?{lat:farm.lat,lon:farm.lon}:HH.coords;
    if(coords.lat===null || coords.lon===null)throw new Error('Choose a mapped field or select coordinates in LOCATION MAP.');
    btn.disabled=true;el.textContent='Connecting to NASA POWER for historical data…';
    const d=await hhApi(`/environment?lat=${encodeURIComponent(coords.lat)}&lon=${encodeURIComponent(coords.lon)}`);
    el.innerHTML=`<h4>NASA POWER · ${esc(d.start)} to ${esc(d.end)}</h4>
      <p><b>Average temperature:</b> ${Number(d.average_temperature_c).toFixed(1)} °C · <b>Rainfall:</b> ${Number(d.total_precipitation_mm).toFixed(1)} mm</p>
      <p>Valid daily temperature samples: ${Number(d.sample_count)} · Field: ${esc(farm?.name||'Selected map pin')}</p>
      <small>${esc(d.note)} No invented readings; verify with local observations.</small>`;
  } catch(err){el.textContent='NASA data unavailable: '+err.message;hhError(err)}
  finally{btn.disabled=false}
};
async function hhReset(scope) {
  const gameOnly=scope==='game';
  const warning=gameOnly?
    'Reset all XP, victories, battles and unlocked plans? Your saved fields and planting/activity records will stay. This cannot be undone.':
    'PERMANENTLY delete ALL your XP, battles, plans, fields, plantings and field activity logs for this profile? This cannot be undone.';
  if(!window.confirm(warning))return;
  if(!window.confirm('Final confirmation: reset '+(gameOnly?'GAME progress only':'EVERYTHING in this profile')+'?'))return;
  try {
    await hhPlayer();
    await hhApi('/progress/reset?scope='+scope,{method:'POST'});
    S={xp:0,w:0,def:{},st:{},log:[]};save();
    B=null;HH.battleId=null;HH.farms=[];HH.plans=[];HH.plantings=[];
    $('#reset-feedback').textContent=gameOnly?'Game progress reset; farming records preserved.':'All profile records reset.';
    await hhSaved();hhStatus('PROGRESS RESET');
  } catch(err){$('#reset-feedback').textContent=err.message;hhError(err)}
}
$('#reset-game').onclick=()=>hhReset('game');
$('#reset-all').onclick=()=>hhReset('all');

$('#copy-code').onclick=async()=>{
  try{await hhPlayer();await navigator.clipboard.writeText(HH.token);$('#saved-status').textContent='Access code copied. Store it privately; anyone with this code can access your saved farm data.'}
  catch(e){hhError(e);$('#saved-status').textContent='Copy unavailable. Use SHOW / RESTORE CODE to select your code.'}
};
$('#show-code').onclick=()=>{$('#code-panel').hidden=!$('#code-panel').hidden;$('#access-code').value=HH.token};
$('#restore-code').onclick=async()=>{
  const old=HH.token,newToken=$('#access-code').value.trim();
  if(!newToken){$('#saved-status').textContent='Enter an access code';return}
  try{HH.token=newToken;await hhApi('/me');localStorage.setItem('harvest-heroes-token',newToken);await hhSaved();$('#saved-status').textContent='Profile restored on this device';hhStatus('PROFILE RESTORED')}
  catch(err){HH.token=old;hhError(err);$('#saved-status').textContent='The access code was not recognized'}
};

hhPlayer().then(()=>hhLoadCrops()).then(()=>hhRefresh()).then(()=>show('dashboard')).catch(hhError);
