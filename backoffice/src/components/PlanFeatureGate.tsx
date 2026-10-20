import {useEffect,useState,type ReactNode} from 'react';
type Client={get:(url:string)=>Promise<{data:{features:Record<string,boolean>}}>};
export default function PlanFeatureGate({companyId,feature,client,children}:{companyId:string;feature:string;client:Client;children:ReactNode}){
 const [state,setState]=useState<'loading'|'allowed'|'denied'|'unavailable'>('loading');
 useEffect(()=>{let current=true;if(!feature){setState('allowed');return;}setState('loading');void client.get(`/subscriptions/access/${companyId}`).then(r=>{if(current)setState(r.data.features[feature]?'allowed':'denied');}).catch(()=>{if(current)setState('unavailable');});return()=>{current=false;};},[companyId,feature,client]);
 if(state==='allowed')return children;
 return <section role="status" className="inventory-form-card">{state==='loading'?'Checking subscription…':state==='denied'?'This feature is not included in your subscription.':'Reconnect to verify this optional feature. Saved transactions are unchanged.'}</section>;
}
