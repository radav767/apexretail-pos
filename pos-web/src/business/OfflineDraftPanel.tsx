import { useCallback, useEffect, useRef, useState } from "react";
import { OfflineOrderOutbox, type OrderCommand } from "./offlineOrders";

type Option={id:string;name:string;product_id?:string};
type Review={entry:OrderCommand;order:{id:string;number?:string;version?:number;status?:string};current_version?:number;current_status?:string};
export default function OfflineDraftPanel({company,employee,device,branch,products,variants,online,send,recoveryOnly=false,queueOnly=false,onChanged}:{
  company:string;employee:string;device:string;branch:string;products:Option[];variants:Option[];online:boolean;
  recoveryOnly?:boolean;queueOnly?:boolean;onChanged?:()=>Promise<unknown>;
  send:(endpoint:string,payload:unknown)=>Promise<unknown>;
}){
  const [product,setProduct]=useState(""),[variant,setVariant]=useState(""),[quantity,setQuantity]=useState("1");
  const [lines,setLines]=useState<{product_id:string;variant_id:string|null;quantity:string;version:number}[]>([]);
  const [entries,setEntries]=useState<OrderCommand[]>([]),[message,setMessage]=useState(""),[busy,setBusy]=useState(false);
  const [review,setReview]=useState<Review|null>(null),[reason,setReason]=useState("");const lock=useRef(false);
  const outbox=useCallback(()=>new OfflineOrderOutbox(localStorage,{company,employee,device}),[company,employee,device]);
  const reload=useCallback(()=>{try{setEntries(outbox().list());}catch(e){setMessage(String(e));}},[outbox]);
  useEffect(()=>{setLines([]);setReview(null);reload();},[reload]);
  async function run(action:()=>Promise<unknown>){
    if(lock.current||!online)return;lock.current=true;setBusy(true);setMessage("");
    try{await action();reload();await onChanged?.();}
    catch(e:any){setMessage(e.response?.data?.detail||e.message||"Original command retained for review");}
    finally{lock.current=false;setBusy(false);}
  }
  async function reviewEntry(entry:OrderCommand){
    const result=await send(entry.endpoint+"/review",{command:entry.payload,reason:"Read-only original command review"}) as any;
    if(typeof result?.order?.id!=="string")throw new Error("No authoritative review returned");
    if(typeof result.already_synchronized==="boolean"){outbox().acknowledge(entry.id,result);setReview(null);return;}
    if(typeof result.current_version!=="number"&&typeof result.current_status!=="string")throw new Error("Server state could not be verified");
    setReview({entry,...result});setReason("");
  }
  return <details className="business-manager" onToggle={reload}><summary>Offline order drafts</summary>
    <p className="business-warning">Unpaid drafts only. Kitchen requests and status changes synchronize after reconnection. Payments require a connection.</p>
    {recoveryOnly&&<p role="status">Recover the current cashier's saved commands. Reconnect to verify permissions before creating orders.</p>}
    {!recoveryOnly&&!queueOnly&&<><form className="business-form" onSubmit={e=>{e.preventDefault();setLines([...lines,{version:1,product_id:product,variant_id:variant||null,quantity}]);}}>
      <label>Product<select required value={product} onChange={e=>{setProduct(e.target.value);setVariant("");}}><option value="">Select product</option>{products.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
      {variants.some(v=>v.product_id===product)&&<label>Variant<select required value={variant} onChange={e=>setVariant(e.target.value)}><option value="">Select variant</option>{variants.filter(v=>v.product_id===product).map(v=><option key={v.id} value={v.id}>{v.name}</option>)}</select></label>}
      <label>Quantity<input required type="number" min="0.001" step="0.001" value={quantity} onChange={e=>setQuantity(e.target.value)}/></label><button disabled={!product||busy}>Add draft item</button>
    </form>{lines.map((line,i)=><p key={i}>{products.find(p=>p.id===line.product_id)?.name} × {line.quantity}</p>)}
    <button disabled={!lines.length||!branch||busy} onClick={async()=>{
      if(lock.current)return;lock.current=true;setBusy(true);
      try{const request=crypto.randomUUID();await outbox().enqueueLicensed({id:request,endpoint:"/operations/offline/drafts",payload:{
        request_id:request,employee_id:employee,captured_at:new Date().toISOString(),
        order:{request_id:crypto.randomUUID(),branch_id:branch,device_id:device,kind:"restaurant",waiter_id:employee},items:lines,
      }},company);setLines([]);setMessage("Draft saved on this device. Not sent to the kitchen.");reload();}catch(e){setMessage(String(e));}finally{lock.current=false;setBusy(false);}
    }}>Save unpaid draft</button></>}
    <button disabled={!online||busy} onClick={()=>void run(()=>outbox().synchronize(send))}>Review & synchronize drafts</button>
    <button disabled={!online||busy} onClick={()=>void run(()=>outbox().recover(send))}>Check server confirmation</button>
    {message&&<p role="status">{message}</p>}
    {entries.map(entry=><article key={entry.id}><strong>{(entry.result as any)?.resolution?"resolved":entry.status}</strong><span> · {entry.endpoint.split("/").at(-1)}</span>
      {entry.error&&<p role="alert">{entry.error}</p>}
      <details><summary>Original draft</summary><pre style={{whiteSpace:"pre-wrap",overflowWrap:"anywhere"}}>{JSON.stringify(entry.payload,null,2)}</pre></details>
      {entry.status!=="acknowledged"&&<button disabled={!online||busy} onClick={()=>void run(()=>reviewEntry(entry))}>Review current server state</button>}
    </article>)}
    {review&&<section className="business-records"><h3>Review current server state</h3>
      <p>{review.order.number||"Original order"} · {review.current_status||review.order.status||"Open"} · {review.current_version? `Version ${review.current_version}`:"Kitchen status"}</p>
      <label>Resolution reason<input maxLength={500} value={reason} onChange={e=>setReason(e.target.value)}/></label>
      <button disabled={!online||busy||reason.trim().length<3} onClick={()=>{
        if(!window.confirm("Accept the current server state WITHOUT applying the queued change? The original command and audit history will be retained."))return;
        void run(async()=>{const result=await send(review.entry.endpoint+"/resolve",{command:review.entry.payload,
          observed_version:review.current_version,observed_status:review.current_status,reason:reason.trim()});
          outbox().acknowledge(review.entry.id,result);setReview(null);setReason("");});
      }}>Accept current server state</button><button disabled={busy} onClick={()=>setReview(null)}>Keep original command</button>
    </section>}
  </details>;
}
