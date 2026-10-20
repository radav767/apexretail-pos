import {useEffect,useState} from 'react';
import {api} from '../api/client';
export default function CommercialBillingPanel({companyId}:{companyId:string}){
 const [data,setData]=useState<any>(null),[message,setMessage]=useState(''),[offset,setOffset]=useState(0);
 useEffect(()=>{setOffset(0);},[companyId]);
 useEffect(()=>{let current=true;void api.get(`/subscriptions/billing/${companyId}?offset=${offset}`).then(r=>{if(current)setData(r.data);}).catch(e=>{if(current)setMessage(e.response?.status===403?'Owner access required for billing history.':'Billing history temporarily unavailable.');});return()=>{current=false;};},[companyId,offset]);
 return <section className="settings-card">
  <h2>Billing history & notices</h2>{message&&<p role="status">{message}</p>}
  {data&&<>
   {data.subscription?.terms&&<article>
    <h3>{data.subscription.terms.plan_name}</h3><p>License · {data.subscription.status}</p>
    <p>Activated · {data.subscription.activation_date||'—'}</p><p>Expiry · {data.subscription.expiry_date||'—'}</p>
    <p>Branches · {data.subscription.terms.branch_limit??'Unlimited'} · Devices · {data.subscription.terms.device_limit??'Unlimited'}</p>
   </article>}
   <div style={{overflowX:'auto'}}><table><thead><tr><th>Plan</th><th>Invoice</th><th>Paid</th><th>Outstanding</th></tr></thead>
    <tbody>{data.invoices.map((r:any)=><tr key={r.id}><td>{r.plan.plan_name}</td><td>{r.currency} {r.amount}</td><td>{r.paid}</td><td>{r.outstanding}</td></tr>)}</tbody>
   </table></div>{!data.invoices.length&&<p>No commercial invoices.</p>}
   <h3>Payment history</h3>{data.payments.map((p:any)=><p key={p.id}>{p.created_at} · {p.currency} {p.amount} · {p.method} · {p.reference}</p>)}
   <h3>Outstanding balances</h3>{data.outstanding_by_currency?.map((r:any)=><p key={r.currency}>{r.currency} {r.amount}</p>)}
   <button disabled={offset===0} onClick={()=>setOffset(Math.max(0,offset-200))}>Newer records</button>
   <button disabled={!data.has_more} onClick={()=>setOffset(offset+200)}>Older records</button>
   {data.notices.map((n:any)=><p key={n.id}>{n.message}</p>)}
  </>}
 </section>;
}
