import {createPrintScope} from "./printing/context";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, getApiErrorMessage } from "./api/client";
import "./business/business.css";
import "./business/business-mobile.css";
export type FocusedFeature = "stock-transfers" | "sales-reports" | "top-products";
type Branch = { id: string; name: string; shop_name: string };
type Product = { product_id: string; product_name?: string; name?: string; quantity: string };
type Variant = { id:string;product_id:string;name:string;sku?:string;stock_qty:string;active:boolean };
type Report = { currency_symbol: string; rows: { label: string; quantity: string; amount: string }[] };
type Transfer = { payload: Record<string, unknown>; confirmed: boolean; retryProtected?: boolean };
function readTransfer(key: string): Transfer | null {
  try {
    const saved=JSON.parse(localStorage.getItem(key)||"null");
    if(saved===null)return null;
    if(!saved || typeof saved!=="object" || !saved.payload || typeof saved.payload!=="object" || typeof saved.confirmed!=="boolean")return {payload:{},confirmed:false};
    return saved;
  }catch{return {payload:{},confirmed:false};}
}
export default function FocusedOperationsPage({ feature, companyId, branchId, identity, permitted, recoveryOnly=false }: {
  feature: FocusedFeature; companyId: string; branchId: string; identity: string; permitted: boolean; recoveryOnly?:boolean;
}) {
  const [branches,setBranches]=useState<Branch[]>([]); const [products,setProducts]=useState<Product[]>([]);
  const [destinations,setDestinations]=useState<Branch[]>([]);
  const [variants,setVariants]=useState<Variant[]>([]);const [variant,setVariant]=useState("");const [variantsReady,setVariantsReady]=useState(false);
  const [source,setSource]=useState(branchId);const [destination,setDestination]=useState("");const [product,setProduct]=useState("");const [quantity,setQuantity]=useState("");
  const [start,setStart]=useState(new Date().toISOString().slice(0,10));const [end,setEnd]=useState(new Date().toISOString().slice(0,10));
  const [report,setReport]=useState<Report|null>(null);const [message,setMessage]=useState("");const [busy,setBusy]=useState(false);const lock=useRef(false);
  const key=`apexretail_transfer_confirmation_v1:${companyId}:${identity}`;
  const [pending,setPending]=useState<Transfer|null>(()=>readTransfer(key));
  useEffect(()=>{setPending(readTransfer(key));},[key]);
  useEffect(()=>{if(recoveryOnly||!permitted||feature!=="stock-transfers")return;let current=true;
    void api.get<Branch[]>(`/inventory/branches/${companyId}`).then(r=>{if(current)setBranches(r.data);}).catch(e=>{if(current)setMessage(getApiErrorMessage(e));});return()=>{current=false;};
  },[companyId,feature,permitted,recoveryOnly]);
  useEffect(()=>{if(recoveryOnly||!permitted||feature!=="stock-transfers")return;let current=true;
    void api.get<Branch[]>(`/inventory/transfer-destinations/${companyId}`).then(r=>{if(current)setDestinations(r.data);}).catch(e=>{if(current)setMessage(getApiErrorMessage(e));});return()=>{current=false;};
  },[companyId,feature,permitted,recoveryOnly]);
  useEffect(()=>{setVariant("");setVariants([]);setVariantsReady(false);if(!product||!source||feature!=="stock-transfers")return;let current=true;
    void api.get<Variant[]>(`/products/variants/${companyId}`,{params:{product_id:product,branch_id:source}}).then(r=>{if(current){setVariants(r.data.filter(v=>v.active));setVariantsReady(true);}}).catch(e=>{if(current){if(e.response?.status===404)setVariantsReady(true);else setMessage(getApiErrorMessage(e));}});return()=>{current=false;};
  },[companyId,source,product,feature]);
  useEffect(()=>{if(!permitted||!source||feature!=="stock-transfers")return;let current=true;
    void api.get<Product[]>(`/inventory/branch-overview/${companyId}`,{params:{branch_id:source}}).then(r=>{if(current)setProducts(r.data);}).catch(e=>{if(current)setMessage(getApiErrorMessage(e));});return()=>{current=false;};
  },[companyId,source,feature,permitted]);
  const params={date_from:start,date_to:end,branch_id:branchId||undefined,view:feature==="top-products"?"product":"individual",limit:50,sort_by:"amount",sort_dir:"desc"};
  async function loadReport(){if(!permitted||start>end)return;setBusy(true);setMessage("");try{setReport((await api.get<Report>(`/reports/sales-history/${companyId}`,{params})).data);}catch(e){setReport(null);setMessage(getApiErrorMessage(e));}finally{setBusy(false);}}
  async function exportCsv(){setBusy(true);try{const r=await api.get(`/reports/sales-history/${companyId}/export.csv`,{params,responseType:"blob"});const url=URL.createObjectURL(r.data);const a=document.createElement("a");a.href=url;a.download=`${feature}.csv`;a.click();URL.revokeObjectURL(url);}catch(e){setMessage(getApiErrorMessage(e));}finally{setBusy(false);}}
  async function transfer(){if(lock.current||!permitted||!navigator.onLine||!variantsReady||(variants.length>0&&!variant))return;lock.current=true;setBusy(true);setMessage("");
    try{if(localStorage.getItem(key)&&localStorage.getItem(key)!=="null")throw new Error("Review the saved transfer before another submission.");
      const requestId=crypto.randomUUID();
      const capabilities=await api.get("/inventory/transfers/capabilities", {timeout:10000}).then(r=>r.data).catch(()=>null);
      if(variant&&!capabilities?.variant_transfers)throw new Error("This server does not support variant transfers. Nothing was submitted.");
      const retryProtected=capabilities?.idempotency==="audit-v1";
      const command={payload:{company_id:companyId,request_id:requestId,source_branch_id:source,destination_branch_id:destination,reference:`POS-${requestId}`,items:[{product_id:product,...(variant?{variant_id:variant}:{}),quantity}]},confirmed:false,retryProtected};
      localStorage.setItem(key,JSON.stringify(command));setPending(command);
      const r=await api.post("/inventory/transfers",command.payload);
      if(!Array.isArray(r.data)||r.data.length!==2||!r.data.every(m=>m.id))throw new Error("Transfer acknowledgement unavailable");
      const ack={...command,confirmed:true};localStorage.setItem(key,JSON.stringify(ack));setPending(ack);setMessage("Stock transfer confirmed.");
    }catch(e){setMessage(getApiErrorMessage(e,"Transfer not confirmed. Do not submit it again; check the original reference."));}finally{lock.current=false;setBusy(false);}}
  async function retryOriginal(){
    if(lock.current||!permitted||!navigator.onLine||!pending?.retryProtected||!pending.payload.request_id||pending.payload.company_id!==companyId)return;
    if(!window.confirm("Submit or recover the original transfer using its protected request identity? Do not create a replacement request."))return;
    lock.current=true;setBusy(true);const recoveryScope=createPrintScope();
    try{
      const capabilities=(await api.get("/inventory/transfers/capabilities", {timeout:10000})).data;
      if(!recoveryScope.isCurrent())return;
      if(capabilities?.idempotency!=="audit-v1"||((pending.payload.items as {variant_id?:string}[])?.some(i=>i.variant_id)&&!capabilities.variant_transfers))throw new Error("This server cannot safely retry the original transfer. Keep it for manager reconciliation.");
      const response=await api.post("/inventory/transfers",pending.payload);
      if(!recoveryScope.isCurrent())return;
      if(!Array.isArray(response.data)||response.data.length!==2||!response.data.every(m=>m.id))throw new Error("Transfer acknowledgement unavailable");
      const ack={...pending,confirmed:true};localStorage.setItem(key,JSON.stringify(ack));setPending(ack);setMessage("Original transfer confirmed.");
    }catch(e){setMessage(getApiErrorMessage(e,"Original transfer retained; request was not confirmed."));}
    finally{lock.current=false;setBusy(false);}
  }
  const check=useCallback(async()=>{if(!pending||!permitted)return;setBusy(true);const recoveryScope=createPrintScope();try{
    if(!pending.payload.reference)throw new Error("Stored transfer requires authorized review; no data was cleared.");
    const r=await api.get(`/inventory/history/${companyId}`,{params:{branch_id:pending.payload.source_branch_id,limit:500}});
    if(!recoveryScope.isCurrent())return;
    const items=pending.payload.items as {product_id:string;variant_id?:string;quantity:string}[];
    const match=r.data.find((m:any)=>m.reference===pending.payload.reference&&m.movement_type==="transfer_out"&&m.product_id===items?.[0]?.product_id&&(m.variant_id||null)===(items?.[0]?.variant_id||null)&&String(m.branch_id)===pending.payload.source_branch_id&&Number(m.quantity)===Number(items[0].quantity));
    if(!match)throw new Error("Transfer not found in recent history. Keep this request and ask an authorized manager to reconcile it; do not resubmit.");
    const ack={...pending,confirmed:true};localStorage.setItem(key,JSON.stringify(ack));setPending(ack);setMessage("Original stock transfer confirmed from history.");
  }catch(e){setMessage(getApiErrorMessage(e));}finally{setBusy(false);}},[companyId,key,pending,permitted]);
  if(!permitted)return <p role="alert">Permission denied.</p>;
  if(recoveryOnly&&(!pending||pending.confirmed))return <p role="status">{pending?"Original transfer confirmation retained.":"No retained transfer request on this POS."}</p>;
  return <section className="business-operations"><h2>{feature==="stock-transfers"?"Stock Transfers":feature==="top-products"?"Top Selling Products":"Sales Reports"}</h2>
    {feature==="stock-transfers"?pending?<><p>{pending.confirmed?"Confirmed":"Awaiting confirmation — do not resubmit"}</p><p>Reference: {String(pending.payload.reference||"Needs review")}</p>{pending.confirmed?<button onClick={()=>{localStorage.setItem(`${key}:ack:${pending.payload.reference}`,JSON.stringify(pending));localStorage.setItem(key,"null");setPending(null);}}>New transfer</button>:<><button disabled={busy} onClick={()=>void check()}>Check original transfer</button>{Boolean(pending.payload.request_id)&&pending.retryProtected&&<button disabled={busy||!navigator.onLine} onClick={()=>void retryOriginal()}>Retry original transfer</button>}</>}</>:<form className="business-form" onSubmit={e=>{e.preventDefault();if(confirm("Transfer the selected stock between branches?"))void transfer();}}>
      <label>Source branch<select required value={source} onChange={e=>{setSource(e.target.value);setProduct("");}}><option value="">Select branch</option>{branches.map(b=><option key={b.id} value={b.id}>{b.shop_name} · {b.name}</option>)}</select></label>
      <label>Destination branch<select required value={destination} onChange={e=>setDestination(e.target.value)}><option value="">Select branch</option>{destinations.filter(b=>b.id!==source).map(b=><option key={b.id} value={b.id}>{b.shop_name} · {b.name}</option>)}</select></label>
      <label>Product<select required value={product} onChange={e=>setProduct(e.target.value)}><option value="">Select product</option>{products.map(p=><option key={p.product_id} value={p.product_id}>{p.product_name||p.name}</option>)}</select></label>
      {variants.length>0&&<label>Variant<select required value={variant} onChange={e=>setVariant(e.target.value)}><option value="">Select variant</option>{variants.map(v=><option key={v.id} value={v.id}>{v.name} · {v.sku||"No SKU"} · {v.stock_qty} available</option>)}</select></label>}
      <label>Quantity<input required type="number" min="0.001" step="0.001" value={quantity} onChange={e=>setQuantity(e.target.value)}/></label><button disabled={busy||source===destination||!variantsReady||(variants.length>0&&!variant)}>Transfer Stock</button></form>:<><form className="business-form" onSubmit={e=>{e.preventDefault();void loadReport();}}><label>From<input required type="date" value={start} onChange={e=>setStart(e.target.value)}/></label><label>To<input required type="date" min={start} value={end} onChange={e=>setEnd(e.target.value)}/></label><button disabled={busy}>View report</button><button type="button" disabled={busy||!report} onClick={()=>void exportCsv()}>Export CSV</button></form>
      <div className="business-records">{report?.rows.map((r,i)=><article key={i}><strong>{r.label}</strong><p>Quantity {r.quantity}</p><p>{report.currency_symbol} {r.amount}</p></article>)}{report&&!report.rows.length&&<p>No matching records</p>}</div></>}
    {message&&<p role="status">{message}</p>}</section>;
}
