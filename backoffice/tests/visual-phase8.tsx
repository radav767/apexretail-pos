// Synthetic browser fixtures only. Never connects to any backend or provider.
import {createRoot} from 'react-dom/client';
import axios,{AxiosError} from 'axios';
import PlatformDashboard from '../src/pages/PlatformDashboard';
import PlanFeatureGate from '../src/components/PlanFeatureGate';
import '../src/index.css';import '../src/theme.css';
const calls:any[]=[];Object.assign(window,{phase8Calls:calls});
let plans:any[]=[],invoices:any[]=[],payments:any[]=[],paymentAttempts=0;
const role=new URLSearchParams(location.search).get('role')||'super_admin';
const client=axios.create({adapter:async config=>{
 const url=config.url||'',body=typeof config.data==='string'?JSON.parse(config.data):config.data;
 calls.push({url,method:config.method,body});let data:any={};
 if(url==='/platform/login')data={mfa_required:true,enrollment_required:true,secret:'SYNTHETICPREVIEWONLY',challenge:'synthetic-challenge-never-a-real-token',expires_in:300};
 else if(url==='/platform/mfa')data={access_token:'apx_platform_synthetic_test_only',admin_id:'synthetic-admin',role};
 else if(url==='/platform/dashboard')data={businesses:12,active_businesses:10,suspended_businesses:2,registered_devices:24,subscriptions:{active:8,trial:3,expired:1},upcoming_renewals:2,revenue:[{currency:'USD',amount:'99.00'}]};
 else if(url.startsWith('/platform/devices?'))data=[{id:'synthetic-device',company_id:'synthetic-company',business:'Synthetic Retail Shop',name:'Checkout 1',status:'active',active:true,app_version:'Preview only',last_seen_at:'2026-10-21T12:00:00Z'}];
 else if(url.includes('/activity')&&url.startsWith('/platform/devices/'))data=[{action:'terminal_registered',created_at:'2026-10-21T10:00:00Z'}];
 else if(url.includes('/status')&&url.startsWith('/platform/devices/'))data={status:'deactivated'};
 else if(url.startsWith('/platform/fiscal?'))data=[{company_id:'synthetic-company',business:'Synthetic Retail Shop',configured:true,environment:'test',device_registration:'not_verified',fiscal_day:null,pending_operation:false,counts:{prepared:4,documents:0},error_events:0,live_submission_enabled:false}];
 else if(url==='/platform/settings')data={version:1,brand_name:'ApexRetail',trial_days:30,default_plan_id:null,renewal_notices:true,business_types:['Retail','Restaurant','Pharmacy']};
 else if(url==='/platform/health')data={api:'responding',database:'reachable',mfa_key:'configured',revision:['p10a_platform_management'],checked_at:'2026-10-21T12:00:00Z',scope:'Synthetic preview — not production monitoring'};
 else if(url.startsWith('/platform/administrators'))data=config.method==='get'?[{id:'synthetic-admin',email:'owner@example.test',role:'super_admin',active:true,mfa_enrolled:true}]:{id:'new-synthetic-admin',...body,mfa_enrolled:false};
 else if(url.startsWith('/platform/sessions'))data=config.method==='get'?[{id:'synthetic-session',admin_id:'synthetic-admin',expires_at:'2026-10-21T12:30:00Z',mfa_verified:true}]:{ok:true};
 else if(url.endsWith('/details'))data={id:'synthetic-company',name:'Synthetic Retail Shop',email:'owner@example.test',business_type:'Retail',active:true,activity:{branches:2,employees:6,devices:3,sales:120,shifts:4}};
 else if(url.endsWith('/recovery-review'))data={status:'identity_review_pending',account_changed:false,next_step:'Owner identity review pending; no account credentials changed.'};
 else if(url.startsWith('/platform/businesses?'))data=[{id:'synthetic-company',name:'Synthetic Retail Shop',email:'synthetic@example.test',status:'active',expiry_date:'2026-12-01T00:00:00Z'}];
 else if(url==='/platform/plans'&&config.method==='get')data=plans;
 else if(url.startsWith('/platform/plans')){
  const plan={id:'synthetic-plan',version:config.method==='put'?2:1,name:body.name,active:true,terms:body};plans=[plan];data=plan;
 }else if(url.includes('/billing'))data={invoices,payments,notices:[]};
 else if(url==='/platform/invoices'){
  const p=plans[0];data={id:'synthetic-invoice',plan:{plan_name:p.name},amount:p.terms.price,currency:p.terms.currency,outstanding:p.terms.price,paid:'0',fulfilled_at:null};invoices=[data];
 }else if(url==='/platform/payments'){
  if(!payments.length){payments=[{id:'synthetic-payment',...body,currency:'USD'}];invoices=invoices.map(i=>({...i,paid:i.amount,outstanding:'0',fulfilled_at:'2026-10-20T12:00:00Z'}));}
  if(paymentAttempts++===0)throw new AxiosError('Network Error','ERR_NETWORK',config);
  data=payments[0];
 }else if(url==='/platform/audit')data=[{id:'synthetic-audit',created_at:'2026-10-20T12:00:00Z',action:'billing_payment_confirmed',details:{synthetic:true}}];
 else if(url.startsWith('/subscriptions/access/'))data={features:{variants:false}};
 return {data:structuredClone(data),status:200,statusText:'OK',headers:{},config};
}});
createRoot(document.getElementById('root')!).render(new URLSearchParams(location.search).has('denied')?
 <PlanFeatureGate companyId="synthetic-company" feature="variants" client={client}><button>Restricted editor must not render</button></PlanFeatureGate>:
 <PlatformDashboard client={client}/>);
