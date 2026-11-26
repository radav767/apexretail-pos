import {useEffect,useRef,useState} from 'react';
import {createPrintScope} from '../printing/context';

type Client={get:(path:string,config:{params:Record<string,string>;responseType:'blob'})=>Promise<{data:Blob}>};
/** Read-only download; a late response must retain the requesting identity. */
export default function ReconciliationExport({companyId,branchId='',client}:{companyId:string;branchId?:string;client:Client}){
 const [start,setStart]=useState(()=>new Date(Date.now()-86400000).toISOString().slice(0,19));
 const [end,setEnd]=useState(()=>new Date().toISOString().slice(0,19));
 const [busy,setBusy]=useState(false),[message,setMessage]=useState('');
 const alive=useRef(true),lock=useRef(false),identity=useRef('');
 identity.current=JSON.stringify([companyId,branchId]);
 useEffect(()=>{alive.current=true;return()=>{alive.current=false}},[]);
 useEffect(()=>{setMessage('');setBusy(false);lock.current=false},[companyId,branchId]);
 async function download(){
  if(lock.current||!companyId)return;
  const from=new Date(start+'Z'),to=new Date(end+'Z');
  if(!Number.isFinite(+from)||!Number.isFinite(+to)||+to<=+from||+to-+from>366*86400000){setMessage('Choose a positive UTC interval of at most 366 days.');return}
  const scope=createPrintScope(),owner=identity.current;
  const current=()=>alive.current&&owner===identity.current&&scope.isCurrent();
  lock.current=true;setBusy(true);setMessage('');
  try{
   const params:Record<string,string>={start:from.toISOString(),end:to.toISOString()};if(branchId)params.branch_id=branchId;
   const {data}=await client.get(`/reports/reconciliation/${companyId}/export.zip`,{params,responseType:'blob'});
   if(!current())return;
   const url=URL.createObjectURL(data),link=document.createElement('a');link.href=url;link.download='reconciliation-v1.zip';link.click();window.setTimeout(()=>URL.revokeObjectURL(url),1000);
   setMessage('Snapshot downloaded. Review manifest and unknown historical values before reconciliation.');
  }catch{if(current())setMessage('Export unavailable. Check permissions, connection and interval; narrow intervals exceeding 10,000 events or receipts.');}
  finally{if(current()){lock.current=false;setBusy(false)}}
 }
 return <section aria-label="Read-only reconciliation export" className="reconciliation-export">
  <h3>Reconciliation snapshot</h3>
  <p>Read-only CSV/JSON bundle. Revenue, tax, payments, collections, debt, refunds, change and FX variance remain separate. No posting or live accounting integration.</p>
  <p>{branchId?'Selected branch only.':'All authorized branches; employees remain scoped to their branch.'} UTC start inclusive, end exclusive; maximum 366 days and 10,000 events/receipts.</p>
  <div style={{display:'flex',flexWrap:'wrap',gap:'1rem',alignItems:'end'}}>
   <label>Export start (UTC)<input type="datetime-local" step="1" value={start} onChange={e=>setStart(e.target.value)} disabled={busy}/></label>
   <label>Export end (UTC)<input type="datetime-local" step="1" value={end} onChange={e=>setEnd(e.target.value)} disabled={busy}/></label>
   <button type="button" disabled={busy||!companyId} onClick={()=>void download()}>{busy?'Preparing snapshot…':'Download reconciliation snapshot'}</button>
  </div><p role="status">{message}</p>
 </section>
}
