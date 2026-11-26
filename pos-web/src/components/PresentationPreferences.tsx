import {useEffect,useRef,useState} from 'react';
import {createPrintScope} from '../printing/context';
type Scope={scope:'company'|'branch'|'device';version:number;preferences:{selector_view?:'table'|'cards'}};
type Effective={effective:{selector_view:'table'|'cards'};sources:{selector_view:string};scopes:Scope[]};
type Client={get:<T>(url:string,config?:any)=>Promise<{data:T}>;put:(url:string,body:unknown)=>Promise<{data:any}>};
/** Domain settings are never mixed with this bounded presentation projection. */
export default function PresentationPreferences({companyId,client,branchId='',deviceId=''}:{companyId:string;client:Client;branchId?:string;deviceId?:string}){
 const [data,setData]=useState<Effective|null>(null),[level,setLevel]=useState<Scope['scope']>('company'),[value,setValue]=useState('inherit'),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
 const [branches,setBranches]=useState<{id:string;name:string}[]>([]),[devices,setDevices]=useState<{id:string;name:string;branch_id:string}[]>([]),[branch,setBranch]=useState(branchId),[device,setDevice]=useState(deviceId);
 const alive=useRef(true),lock=useRef(false),generation=useRef(0),pending=useRef<Record<string,unknown>|null>(null);
 const identity=JSON.stringify([companyId,branch,device,level]),identityRef=useRef(identity);identityRef.current=identity;
 useEffect(()=>{alive.current=true;return()=>{alive.current=false;generation.current++}},[]);
 useEffect(()=>{const scope=createPrintScope();let active=true;void Promise.all([client.get<{id:string;name:string}[]>(`/devices/branches/${companyId}`),client.get<{id:string;name:string;branch_id:string}[]>(`/devices/${companyId}`)]).then(([b,d])=>{if(active&&scope.isCurrent()){setBranches(b.data);setDevices(d.data)}}).catch(()=>{});return()=>{active=false}},[companyId,client]);
 useEffect(()=>{const scope=createPrintScope(),epoch=++generation.current,owner=identity;setData(null);setMessage('');pending.current=null;lock.current=false;setBusy(false);
  const params:Record<string,string>={};if(level!=='company'&&branch)params.branch_id=branch;if(level==='device'&&device)params.device_id=device;
  if(level!=='company'&&!branch||level==='device'&&!device)return;
  void client.get<Effective>(`/settings/preferences/${companyId}`,{params}).then(({data})=>{if(alive.current&&epoch===generation.current&&owner===identityRef.current&&scope.isCurrent()){setData(data);setValue(data.scopes.find(s=>s.scope===level)?.preferences.selector_view||'inherit')}}).catch(()=>{if(alive.current&&epoch===generation.current&&scope.isCurrent())setMessage('Cannot load preferences with the current account.')});
 },[companyId,client,identity,level,branch,device]);
 async function save(){if(!data||lock.current)return;const scope=createPrintScope(),owner=identity,epoch=generation.current,current=()=>alive.current&&owner===identityRef.current&&epoch===generation.current&&scope.isCurrent();
  const body=pending.current||{company_id:companyId,request_id:crypto.randomUUID(),scope:level,...(level!=='company'?{branch_id:branch}:{}),...(level==='device'?{device_id:device}:{}),version:data.scopes.find(s=>s.scope===level)?.version||0,preferences:value==='inherit'?{}:{selector_view:value}};
  pending.current=body;lock.current=true;setBusy(true);setMessage('');
  try{const result=await client.put(`/settings/preferences/${companyId}`,body);if(!current())return;pending.current=null;const scopes=[...data.scopes.filter(s=>s.scope!==level),{scope:level,version:result.data.version,preferences:result.data.payload.preferences}];let view:'table'|'cards'='table',source='default';for(const scopeName of ['company','branch','device']){const entry=scopes.find(s=>s.scope===scopeName);if(entry?.preferences.selector_view){view=entry.preferences.selector_view;source=scopeName}}setData({...data,scopes,effective:{selector_view:view},sources:{selector_view:source}});setMessage('Presentation preferences saved. Reopen product search to apply.');window.dispatchEvent(new Event('selector-preferences-changed'));}
  catch{if(current())setMessage('Save not confirmed. Retry retains the original request. Reload this section to review a conflicting version.');}
  finally{if(current()){lock.current=false;setBusy(false)}}
 }
 return <section aria-label="Product search preferences"><h3>Product search presentation</h3><p>Company defaults → branch override → device override. Empty overrides inherit. This affects search results only; payment, security, stock and terminal behavior stay governed by their existing settings.</p>
  <label>Preference scope<select aria-label="Preference scope" value={level} disabled={busy||!!pending.current} onChange={e=>setLevel(e.target.value as Scope['scope'])}><option value="company">Company defaults</option><option value="branch">Branch override</option><option value="device">Device override</option></select></label>
  {level!=='company'&&<label>Preference branch<select aria-label="Preference branch" value={branch} disabled={busy||!!pending.current} onChange={e=>{setBranch(e.target.value);setDevice('')}}><option value="">Choose branch</option>{branches.map(b=><option key={b.id} value={b.id}>{b.name}</option>)}</select></label>}
  {level==='device'&&<label>Preference device<select aria-label="Preference device" value={device} disabled={busy||!!pending.current} onChange={e=>setDevice(e.target.value)}><option value="">Choose device</option>{devices.filter(d=>d.branch_id===branch).map(d=><option key={d.id} value={d.id}>{d.name}</option>)}</select></label>}
  <label>Product search view<select aria-label="Product search view" disabled={!data||busy||!!pending.current} value={value} onChange={e=>setValue(e.target.value)}><option value="inherit">Inherit default</option><option value="table">Table</option><option value="cards">Cards</option></select></label>
  {data&&<p>Current effective view: {data.effective.selector_view} · from {data.sources.selector_view}. Scope version {data.scopes.find(s=>s.scope===level)?.version||0}.</p>}
  <button type="button" disabled={!data||busy} onClick={()=>void save()}>{busy?'Saving…':pending.current?'Retry original preference save':'Save presentation preferences'}</button><p role="status">{message}</p>
 </section>
}
