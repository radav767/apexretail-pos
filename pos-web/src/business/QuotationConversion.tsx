import {useEffect,useRef,useState} from 'react';
import {createPrintScope} from '../printing/context';
import type {PricingPlan} from './QuotationPricing';
type Quote={id:string;version:number;kind:string;status:string;quotation_terms?:PricingPlan|null};
type Intent={version:number;charge_to_room:false;payment:{company_id:string;items:never[];payment_method:'cash'|'credit';tendered_amount_original:string|null}};
export default function QuotationConversion<T extends Quote>({order,companyId,actorKey,client,disabled,onChanged,onSaleCompleted}:{order:T;companyId:string;actorKey:string;client:{post:<R>(path:string,data:unknown)=>Promise<{data:R}>};disabled:boolean;onChanged:(row:T)=>void;onSaleCompleted?:(id:string)=>Promise<void>}){
 const actor=actorKey==='backoffice'?sessionStorage.getItem('backoffice_user_id')||'':actorKey,key=`apexretail_quotation_conversion_v2:${companyId}:${actor}:${order.id}`;
 const [pending,setPending]=useState<Intent|null>(null),[method,setMethod]=useState<'cash'|'credit'>('cash'),[received,setReceived]=useState(''),[busy,setBusy]=useState(false),[blocked,setBlocked]=useState(false),[message,setMessage]=useState('');const alive=useRef(true),lock=useRef(false);
 useEffect(()=>{alive.current=true;setPending(null);setBlocked(false);try{const raw=sessionStorage.getItem(key);if(raw){if(raw.length>2000)throw Error();const v=JSON.parse(raw) as Intent;
  if(!Number.isInteger(v.version)||v.version<1||v.charge_to_room!==false||v.payment.company_id!==companyId||!Array.isArray(v.payment.items)||v.payment.items.length||!['cash','credit'].includes(v.payment.payment_method)||!(v.payment.tendered_amount_original===null||typeof v.payment.tendered_amount_original==='string'&&/^\d{1,12}(\.\d{1,4})?$/.test(v.payment.tendered_amount_original))||Object.keys(v).some(k=>!['version','charge_to_room','payment'].includes(k))||Object.keys(v.payment).some(k=>!['company_id','items','payment_method','tendered_amount_original'].includes(k)))throw Error();setPending(v)}}catch{setBlocked(true);setMessage('Retained quotation payment needs review. Nothing was removed.')}return()=>{alive.current=false}},[key,companyId]);
 async function convert(){if(disabled||busy||blocked||!actor||!navigator.onLine||lock.current)return;lock.current=true;setBusy(true);const scope=createPrintScope(),current=()=>alive.current&&scope.isCurrent();
  try{const command=pending||{version:order.version,charge_to_room:false as const,payment:{company_id:companyId,items:[] as never[],payment_method:method,tendered_amount_original:method==='cash'?received:null}};
   if(command.payment.payment_method==='cash'&&!/^\d{1,12}(\.\d{1,4})?$/.test(command.payment.tendered_amount_original||''))throw Error();sessionStorage.setItem(key,JSON.stringify(command));setPending(command);
   const {data}=await client.post<{sale_id:string;order:T;already_settled:boolean}>(`/operations/orders/${order.id}/settle`,command);if(!current())return;
   if(data.order.id!==order.id||data.order.status!=='settled'||data.order.kind!=='quotation'||(data.order as T&{sale_id?:string}).sale_id!==data.sale_id)throw Error();
   sessionStorage.removeItem(key);setPending(null);onChanged(data.order);setMessage(data.already_settled?'Original quotation payment recovered. No new stock or payment effect.':'Quotation converted. Payment recorded once.');
   if(!data.already_settled&&onSaleCompleted&&current())await onSaleCompleted(data.sale_id);
  }catch{if(current())setMessage('Quotation conversion not confirmed. Original payment input retained; retry it before another payment.')}
  finally{lock.current=false;if(current())setBusy(false)}
 }
 const plan=order.quotation_terms;if(!plan)return null;
 return <section aria-label="Accepted quotation payment"><h3>Accepted quotation payment</h3><p>Total {plan.total} {plan.currency}; cash amount {plan.display_total} {plan.display_currency} at accepted rate {plan.exchange_rate_snapshot}. Credit records base-currency debt. Stock is checked at conversion.</p>{message&&<p role="status" aria-live="polite">{message}</p>}
 {pending?<button type="button" disabled={disabled||busy||blocked} onClick={()=>void convert()}>Recover original quotation payment</button>:order.status==='open'&&<><fieldset disabled={disabled||busy||blocked}><legend>Record accepted payment</legend><label>Quotation payment method<select aria-label="Quotation payment method" value={method} onChange={e=>setMethod(e.target.value as 'cash'|'credit')}><option value="cash">cash</option><option value="credit">credit</option></select></label>{method==='cash'&&<label>Cash tendered in {plan.display_currency}<input type="number" min="0" step="0.0001" value={received} onChange={e=>setReceived(e.target.value)}/></label>}<button type="button" disabled={method==='cash'&&!received} onClick={()=>void convert()}>Confirm accepted quotation payment</button></fieldset></>}
 </section>;
}
