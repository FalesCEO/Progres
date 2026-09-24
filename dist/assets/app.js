import config from './config.js';
import { normalizeApiOrigin } from './api-config.mjs';
const storageKey = 'fales-api-origin:' + new URL('../', import.meta.url).pathname;
let savedOrigin = '';
try { savedOrigin = localStorage.getItem(storageKey) || ''; } catch {}
let apiOrigin = config.mode === 'server' ? location.origin : '';
try { if (savedOrigin || config.apiOrigin) apiOrigin = normalizeApiOrigin(savedOrigin || config.apiOrigin, location.protocol); } catch {}
const $ = id => document.getElementById(id);
const state = {task:null, result:null, history:[], busy:false, attempted:false, changed:false};
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const prefix = [[1e9,'G'],[1e6,'M'],[1e3,'k'],[1,''],[1e-3,'m'],[1e-6,'µ'],[1e-9,'n'],[1e-12,'p'],[1e-15,'f']];
function scale(value, unit){if(!['m','H','F','s','A','V','W','Ω','S','Hz','Hz/V'].includes(unit))return [1,unit==='deg'?'°':unit];let [factor,p] = prefix.find(([f])=>Math.abs(value)>=f*.9999)||prefix.at(-1);return [factor,p+unit];}
function fmt(v,unit){if(v===null||v===undefined)return '—';let [factor,u]=scale(v,unit);return `${Number((v/factor).toPrecision(4))} ${u}`;}
function target(m,v){if(m.direction==='eq')return `${fmt(v*m.tolerance,m.unit)} – ${fmt(v/m.tolerance,m.unit)}`;return `${m.direction==='min'?'≥':'≤'} ${fmt(v,m.unit)}`;}
function notify(text,error=false){$('notice').hidden=!text;$('notice').className='notice'+(error?' error':'');$('notice').textContent=text;}
async function api(path,body){if(!apiOrigin)throw new Error('Connect a simulator API to generate tasks and run SPICE.');const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),100000);try{const r=await fetch(apiOrigin+'/api/'+path,{method:body?'POST':'GET',headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined,signal:controller.signal});if(!r.headers.get('content-type')?.includes('application/json'))throw new Error('This address is not a Fales API. Check the simulator connection.');const data=await r.json();if(!r.ok)throw new Error(typeof data.detail==='string'?data.detail:'Please enter valid numeric values for every field.');return data;}catch(e){if(e.name==='AbortError')throw new Error('The request timed out. Please try again.');if(e instanceof TypeError)throw new Error('Cannot reach the simulator. Check its address, availability, and allowed website origin.');throw e;}finally{clearTimeout(timer);}}
function busy(on,message=''){state.busy=on;for(const id of ['generate','topology','task-type','run','reference','api-connect','api-reset','api-origin'])$(id).disabled=on;document.querySelectorAll('#parameters input').forEach(e=>e.disabled=on||(state.task?.task_type==='analyze'&&Boolean(state.result)));$('generate').classList.toggle('busy',on);if(message)notify(message);$('run').textContent=on?'Running SPICE simulation…':state.task?.task_type==='analyze'?'Verify prediction →':'Run SPICE →';if(!on&&state.task?.task_type==='analyze'&&state.result)$('run').disabled=true;}
function details(task){return `<details><summary>Inspect circuit & physics</summary><p>${esc(task.hint)}</p><pre>${esc(task.models)}\n\n${esc(task.skeleton)}</pre></details>`;}
function fields(task){const analyze=task.task_type==='analyze';const items=analyze?task.metrics.map(m=>({name:m.name,label:m.label,unit:m.unit,value:null,bounds:m.sanity})):task.parameters;return `<div class="param-title">${analyze?'PREDICT THE MEASUREMENTS':'EDITABLE CIRCUIT PARAMETERS'}</div><div class="param-grid">${items.map(p=>{const [factor,unit]=scale(p.value??Math.sqrt(p.bounds[0]*p.bounds[1]),p.unit);return `<div class="param"><label for="param-${esc(p.name)}">${esc(p.label||p.name)}</label><div class="input-wrap"><input id="param-${esc(p.name)}" name="${esc(p.name)}" data-factor="${factor}" type="number" step="any" ${analyze?'min="0"':`min="${p.bounds[0]/factor}" max="${p.bounds[1]/factor}"`} value="${p.value===null?'':Number((p.value/factor).toPrecision(12))}" required autocomplete="off" aria-describedby="range-${esc(p.name)}"><span>${esc(unit)}</span></div><small id="range-${esc(p.name)}">${analyze?'Your analytical prediction':`${Number((p.bounds[0]/factor).toPrecision(4))} – ${Number((p.bounds[1]/factor).toPrecision(4))} ${esc(unit)}`}</small></div>`;}).join('')}</div>`;}
function renderTask(){const t=state.task,analysis=t.task_type==='analyze';$('task-label').textContent=t.id.slice(0,8).toUpperCase();$('proposal-title').textContent=analysis?'Predict circuit behavior':'Propose a solution';$('problem').innerHTML=`<h3 class="task-heading">${esc(t.title)}</h3><p class="task-description">${analysis?'The circuit is fixed. Predict its measurements without a simulator, then submit once to compare with real SPICE ground truth.':t.task_type==='debug'?'Exactly one parameter is corrupted. Find and repair it to meet every specification.':'Choose the circuit parameters to meet every target below.'}</p>${analysis?`<details open><summary>Given circuit parameters</summary><pre>${t.parameters.map(p=>`${p.name.padEnd(5)} ${fmt(p.value,p.unit)}`).map(esc).join('\n')}</pre></details>`:`<div class="specs">${t.metrics.map(m=>`<div class="spec"><span>${esc(m.label)}</span><strong>${esc(m.direction==='eq'?fmt(t.targets[m.name],m.unit):target(m,t.targets[m.name]))}</strong>${m.direction==='eq'?`<small>Allowed: ${esc(target(m,t.targets[m.name]))}</small>`:''}</div>`).join('')}</div>`}${details(t)}`;$('parameters').innerHTML=fields(t);$('solution-form').hidden=false;$('reference').hidden=true;$('reference').textContent=analysis?'Show measured answer':'Load valid solution';$('run-caption').textContent=analysis?'Single-shot analysis. Ground truth was simulated during task generation.':'Your parameters. A real simulation. An objective result.';$('generate').innerHTML='Generate New Task <span>↗</span>';renderResults();}
function renderResults(){const t=state.task,r=state.result,analysis=t.task_type==='analyze';$('result-state').textContent=state.changed?'AWAITING RE-RUN':r?(r.solved?'TASK SOLVED':'NOT SOLVED'):'READY TO VERIFY';$('result-state').className='tag'+(r&&!state.changed?(r.solved?' solved':' failed'):'');if(!r){$('results').innerHTML=`<div class="empty"><div class="empty-symbol">${analysis?'≈':'↳'}</div><h3>${analysis?'What will physics say?':'Ready when you are.'}</h3><p>${analysis?'Enter your predictions, then reveal how closely they match ngspice.':'Adjust the parameters on the left and run SPICE to see which specifications your design meets.'}</p><div class="reward-placeholder"><span>REWARD</span><strong>—<small> / 1.50</small></strong></div></div>`;return;}
$('results').innerHTML=`${state.changed?'<div class="stale">Parameters changed. Results below belong to the previous attempt. Run SPICE again.</div>':''}<table class="result-table"><thead><tr><th>METRIC</th><th>${analysis?'PREDICTED':'TARGET'}</th><th>MEASURED</th><th aria-label="Pass or fail"></th></tr></thead><tbody>${r.comparisons.map(row=>{const m=t.metrics.find(m=>m.name===row.name);return `<tr><td>${esc(m.label)}</td><td>${esc(analysis?fmt(row.target,m.unit):target(m,row.target))}</td><td>${esc(fmt(row.value,m.unit))}</td><td class="${row.passed?'pass':'fail'}" aria-label="${row.passed?'Passed':'Failed'}">${row.passed?'✓':'✕'}</td></tr>`;}).join('')}</tbody></table><div class="reward-card ${r.solved?'':'failed'}"><div class="reward-top"><span>FALES REWARD</span><strong class="reward-value">${r.reward.toFixed(3)}<small> / 1.50</small></strong></div><div class="verdict">${r.solved?'✓ TASK SOLVED':'✕ REQUIREMENTS NOT MET'}</div></div>${r.error?`<p class="result-error">${esc(r.error)}</p>`:''}<div class="result-meta">${r.measured?analysis?'Verified against generation-time ngspice measurements':`Verified by ngspice · Simulation: ${r.simulation_ms} ms`:r.legality.valid?'Simulation unsuccessful · No measurements':'Rejected before simulation · Illegal parameters'}<br>Engine fingerprint: ${esc(r.fingerprint)}${analysis?'<br>Pass threshold: min(predicted, actual) / max(predicted, actual) ≥ 0.90':''}</div>${state.history.length>1?`<div class="history"><p>YOUR VERIFICATION TRAJECTORY</p>${state.history.map((x,i)=>`<div class="history-row"><span>Attempt ${i+1}</span><span>${x.reward.toFixed(3)} ${x.solved?'✓':'·'}</span></div>`).join('')}</div>`:''}`;}
$('generate').addEventListener('click',async()=>{if(state.busy)return;busy(true,'Generating a new task with real ngspice. Complex circuits can take up to 90 seconds…');try{const task=await api('generate',{topology:$('topology').value,task_type:$('task-type').value});Object.assign(state,{task,result:null,history:[],attempted:false,changed:false});renderTask();notify('Task generated from a real, simulated solution. Your turn.');}catch(e){notify(e.message,true);}finally{busy(false);}});
$('solution-form').addEventListener('submit',async e=>{e.preventDefault();if(state.busy)return;const parameters={};for(const input of document.querySelectorAll('#parameters input'))parameters[input.name]=Number(input.value)*Number(input.dataset.factor);busy(true,state.task.task_type==='analyze'?'Comparing your predictions with measured ground truth…':'Running SPICE simulation…');try{const r=await api('evaluate',{task_id:state.task.id,parameters});state.result=r;state.history.push(r);state.changed=false;state.attempted=true;renderResults();$('reference').hidden=false;notify('');}catch(e){notify(e.message,true);}finally{busy(false);}});
$('parameters').addEventListener('input',()=>{if(state.result){state.changed=true;renderResults();}});
$('reference').addEventListener('click',async()=>{if(state.busy)return;busy(true);try{const ref=await api('reference-solution',{task_id:state.task.id});for(const input of document.querySelectorAll('#parameters input'))input.value=Number((ref.parameters[input.name]/Number(input.dataset.factor)).toPrecision(12));if(state.task.task_type==='analyze'){notify('Measured answer revealed. Generate a new task for another single-shot prediction.');}else{state.changed=true;renderResults();notify('Valid solution loaded. Run SPICE to independently verify it.');}}catch(e){notify(e.message,true);}finally{busy(false);}});
for(const id of ['topology','task-type'])$(id).addEventListener('change',()=>{if(state.task)notify('Selection changed. Generate a new task to apply it; the current task keeps its original circuit and requirements.');});
function showCatalog(c){
  $('topology').innerHTML=c.topologies.map(t=>`<option value="${esc(t.id)}">${esc(t.label)}</option>`).join('');
  $('task-type').innerHTML=c.task_types.map(t=>`<option value="${esc(t.id)}">${esc(t.label)}</option>`).join('');
  $('coverage').textContent=`${c.topologies.length} topologies · ${c.task_types.length} task types`;
}
$('api-form').addEventListener('submit',async e=>{
  e.preventDefault(); if(state.busy)return;
  const previous=apiOrigin;
  try{
    apiOrigin=normalizeApiOrigin($('api-origin').value,location.protocol);
    $('api-connect').disabled=true; $('api-status').textContent='Checking simulator connection…';
    const c=await api('catalog');
    if(!Array.isArray(c.topologies)||!Array.isArray(c.task_types))throw new Error('This server is not a compatible Fales API.');
    if(!c.simulator_available)throw new Error('The API is reachable, but ngspice is not installed on that server.');
    try{localStorage.setItem(storageKey,apiOrigin);}catch{throw new Error('Browser storage is unavailable. Configure FALES_API_URL in the site deployment instead.');}
    location.reload();
  }catch(err){apiOrigin=previous; $('api-status').textContent=err.message; $('api-connect').disabled=false;}
});
$('api-reset').addEventListener('click',()=>{try{localStorage.removeItem(storageKey);}catch{} location.reload();});
async function init(){
  $('api-settings').hidden=config.mode!=='pages';
  $('api-origin').value=apiOrigin;
  if(config.catalog)showCatalog(config.catalog);
  if(!apiOrigin){
    $('connection').textContent='Simulator not connected';
    $('api-settings').open=true;
    $('api-status').textContent='No simulator has been configured for this site yet.';
    notify('The website is ready. A connected simulator is required for live task generation and verification.');
    return;
  }
  try{
    const c=await api('catalog');showCatalog(c);
    $('connection').textContent=c.simulator_available?'ngspice available':'ngspice unavailable';
    $('live-dot').classList.toggle('ready',c.simulator_available);busy(false);
    $('generate').disabled=!c.simulator_available;
    $('api-status').textContent='Connected to '+apiOrigin;
    if(!c.simulator_available)notify('ngspice is not installed on this server. Install it to enable real verification.',true);
  }catch(e){notify(e.message,true);$('connection').textContent='Connection unavailable';$('api-settings').hidden=false;$('api-settings').open=true;}
}
init();
