import {createPrintScope} from "../../../pos-web/src/printing/context";
import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";

type Api={get:(url:string,config?:any)=>Promise<{data:any}>;post:(url:string,data?:unknown)=>Promise<{data:any}>};
type Lot={id:string;code:string;expires_on:string;quantity:string};
type Position={key:string;product_id:string;variant_id:string|null;name:string;sku:string|null;unit:string;stock_qty:string;active:boolean;batches:Lot[]};
type Pending={endpoint:string;payload:Record<string,unknown>;confirmed:boolean;rejected?:boolean};
function read(key:string):Pending|null{
  try{const value=JSON.parse(localStorage.getItem(key)||"null");if(value===null)return null;
    return value&&typeof value==="object"&&value.payload&&typeof value.confirmed==="boolean"?value:{endpoint:"",payload:{},confirmed:false};}
  catch{return {endpoint:"",payload:{},confirmed:false};}
}
export default function StockTakePanel({companyId,branchId,onDataChanged,client=api,identity="backoffice",permitted=true,recoveryOnly=false}:{
  companyId:string;branchId:string;onDataChanged?:()=>void;client?:Api;identity?:string;permitted?:boolean;recoveryOnly?:boolean;
}){
  const [products,setProducts]=useState<Position[]>([]),[counts,setCounts]=useState<Record<string,string>>({});
  const [reference,setReference]=useState(""),[notes,setNotes]=useState(""),[message,setMessage]=useState(""),[loading,setLoading]=useState(false);
  const [lotCounts,setLotCounts]=useState<Record<string,string>>({});
  const key=`apexretail_stock_count_v1:${companyId}:${branchId}:${identity}`;
  const [pending,setPending]=useState<Pending|null>(()=>read(key));const lock=useRef(false);
  useEffect(()=>{setPending(read(key));setCounts({});setLotCounts({});},[key]);
  async function loadProducts(){
    if(recoveryOnly||!permitted||!branchId)return;
    setLoading(true);
    try{setProducts((await client.get(`/inventory/count-catalog/${companyId}`,{params:{branch_id:branchId}})).data);}
    catch(e:any){setMessage(e.response?.data?.detail||"Cannot load physical stock positions");}
    finally{setLoading(false);}
  }
  useEffect(()=>{let current=true;setProducts([]);if(recoveryOnly||!permitted||!branchId)return;
    setLoading(true);void client.get(`/inventory/count-catalog/${companyId}`,{params:{branch_id:branchId}}).then(r=>{if(current)setProducts(r.data);})
      .catch(e=>{if(current)setMessage(e.response?.data?.detail||"Cannot load physical stock positions");}).finally(()=>{if(current)setLoading(false);});
    return()=>{current=false;};
  },[companyId,branchId,client,permitted,recoveryOnly]);
  const counted=products.filter(p=>!p.batches.length&&counts[p.key]!==undefined&&counts[p.key]!=="");
  function archive(command:Pending){
    localStorage.setItem(`${key}:archive:${String(command.payload.request_id)}`,JSON.stringify(command));
    localStorage.setItem(key,"null");setPending(null);setCounts({});setLotCounts({});
  }
  async function submit(command:Pending){
    if(lock.current||!permitted||!navigator.onLine)return;
    if(!["/inventory/stock-take","/operations/batches/stock"].includes(command.endpoint)||!command.payload.request_id||(command.payload.company_id!==companyId&&command.endpoint==="/inventory/stock-take")||command.payload.branch_id!==branchId){
      setMessage("Saved count needs authorized review. Nothing was deleted.");return;
    }
    lock.current=true;setLoading(true);const recoveryScope=createPrintScope();
    try{
      const caps=(await client.get("/inventory/stock-take/capabilities",{timeout:10000})).data;
      if(!recoveryScope.isCurrent())return;
      if(caps.idempotency!=="audit-v1"||!caps.variant_counts||!caps.expected_quantity)throw new Error("This server cannot safely apply the count");
      const response=(await client.post(command.endpoint,command.payload)).data;
      if(!recoveryScope.isCurrent())return;
      if(!(Array.isArray(response)&&response.length>0&&response.every(m=>m.id))&&!(response?.movement_id&&response?.batch_id))throw new Error("No authoritative stock count acknowledgement");
      const ack={...command,confirmed:true};localStorage.setItem(key,JSON.stringify(ack));setPending(ack);setMessage("Stock count confirmed.");
      await loadProducts();onDataChanged?.();
    }catch(e:any){
      if(!recoveryScope.isCurrent())return;
      const detail=e.response?.data?.detail;
      if(e.response?.status===409&&typeof detail==="string"&&detail.startsWith("Stock changed since")){
        const rejected={...command,rejected:true};localStorage.setItem(key,JSON.stringify(rejected));setPending(rejected);
      }
      setMessage(typeof detail==="string"?detail:e.message||"Count not confirmed. Original request retained.");
    }finally{lock.current=false;setLoading(false);}
  }
  async function start(lot?:{position:Position;batch:Lot}){
    if(lock.current||pending||!navigator.onLine||!permitted)return;
    const entries=lot?[]:counted;
    if(!lot&&!entries.length){setMessage("Enter at least one physical quantity");return;}
    const quantities=lot?[lotCounts[lot.batch.id]]:entries.map(p=>counts[p.key]);
    if(quantities.some(v=>v===""||v===undefined||!Number.isFinite(Number(v))||Number(v)<0)){setMessage("Physical quantities must be zero or greater");return;}
    if(!window.confirm("Apply the actual quantities counted? This changes inventory, not payments."))return;
    const command:Pending=lot?{endpoint:"/operations/batches/stock",confirmed:false,payload:{
      request_id:crypto.randomUUID(),branch_id:branchId,product_id:lot.position.product_id,variant_id:lot.position.variant_id,
      operation:"count",code:lot.batch.code,expires_on:lot.batch.expires_on,expected_qty:String(lot.batch.quantity),
      quantity:lotCounts[lot.batch.id],reason:notes.trim()||"Physical batch count"
    }}:{endpoint:"/inventory/stock-take",confirmed:false,payload:{
      company_id:companyId,branch_id:branchId,request_id:crypto.randomUUID(),reference:reference.trim()||null,notes:notes.trim()||null,
      items:entries.map(p=>({product_id:p.product_id,variant_id:p.variant_id,expected_qty:String(p.stock_qty),physical_qty:counts[p.key]}))
    }};
    try{if(read(key))throw new Error("Review the saved count first");
      localStorage.setItem(key,JSON.stringify(command));setPending(command);await submit(command);
    }catch(e:any){setMessage(e.message||"Cannot preserve the stock count. Nothing was submitted.");}
  }
  if(!permitted)return <p role="alert">Permission denied.</p>;
  if(recoveryOnly&&(!pending||pending.confirmed||pending.rejected))return <p role="status">{pending?"Original count evidence retained. Continue review in Backoffice; no replacement count was created.":"No retained count request on this POS."}</p>;
  return <section className="inventory-form-card"><div className="inventory-panel-header stock-take-header"><h2>Stock Take</h2>
    {!pending&&<div className="stock-take-header-actions"><button disabled={loading} onClick={()=>setCounts(Object.fromEntries(products.filter(p=>!p.batches.length).map(p=>[p.key,String(p.stock_qty)])))}>Fill system quantities</button>
    <button disabled={loading} onClick={()=>setCounts({})}>Clear counts</button></div>}</div>
    {pending?<><p>{pending.confirmed?"Stock count confirmed":pending.rejected?"Count rejected — stock changed":"Awaiting original count confirmation"}</p>
      <details><summary>Original count</summary><pre style={{whiteSpace:"pre-wrap",overflowWrap:"anywhere"}}>{JSON.stringify(pending.payload,null,2)}</pre></details>
      {pending.confirmed?<button onClick={()=>archive(pending)}>New stock count</button>:pending.rejected?<button disabled={loading} onClick={()=>{
        if(window.confirm("Archive this rejected count and physically recount using current quantities?")){archive(pending);void loadProducts();}
      }}>Archive rejected count and recount</button>:<button disabled={loading||!navigator.onLine} onClick={()=>void submit(pending)}>Retry original count</button>}
    </>:<><div className="stock-take-details"><label>Stock-take reference<input value={reference} onChange={e=>setReference(e.target.value)}/></label><label>Notes<input value={notes} onChange={e=>setNotes(e.target.value)}/></label></div>
      <div className="inventory-table-wrapper"><table><thead><tr><th>Product / variant</th><th>SKU</th><th>Unit</th><th>System Quantity</th><th>Physical Quantity</th><th>Variance</th></tr></thead><tbody>
      {products.map(p=><tr key={p.key}><td><strong>{p.name}</strong>{!p.active&&<small>Inactive variant</small>}</td><td>{p.sku||"—"}</td><td>{p.unit}</td><td>{p.stock_qty}</td>
        <td>{p.batches.length?<details><summary>Count selected batches</summary>{p.batches.map(lot=><div key={lot.id}><strong>{lot.code}</strong><span> · {lot.expires_on} · {lot.quantity} recorded</span>
          <input aria-label={`Physical batch count ${p.name} ${lot.code}`} type="number" min="0" step="0.001" value={lotCounts[lot.id]??""} onChange={e=>setLotCounts({...lotCounts,[lot.id]:e.target.value})}/>
          <button disabled={loading||!navigator.onLine} onClick={()=>void start({position:p,batch:lot})}>Apply batch count</button></div>)}</details>:
          <input className="physical-count-input" aria-label={`Physical count ${p.name}`} type="number" min="0" step="0.001" value={counts[p.key]??""} onChange={e=>setCounts({...counts,[p.key]:e.target.value})}/>}</td>
        <td>{p.batches.length||counts[p.key]===undefined||counts[p.key]===""?"—":Number(counts[p.key])-Number(p.stock_qty)}</td></tr>)}
      </tbody></table></div><button className="inventory-primary-button" disabled={loading||!navigator.onLine||!counted.length} onClick={()=>void start()}>Complete Stock Take ({counted.length})</button></>}
      {message&&<p className="inventory-message" role="status">{message}</p>}
    </section>;
}
