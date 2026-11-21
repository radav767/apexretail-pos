import { useEffect, useRef, useState } from "react";
import { createBootstrapScope } from "../api/authLifecycle";
type Intent={request_id:string;version:number;reason:string};
type Quote={id:string;kind:string;version:number;parent_id?:string|null;quotation_command_ack?:string};
export default function QuotationRevision<T extends Quote>({order,companyId,actorKey,client,onChanged,onPending,disabled}:{order:T;companyId:string;actorKey:string;client:{post:<R>(path:string,data:unknown)=>Promise<{data:R}>};onChanged:(order:T)=>void;onPending:(pending:boolean)=>void;disabled:boolean}){
  const actor=actorKey==="backoffice"?sessionStorage.getItem("backoffice_user_id")||"":actorKey;
  const key=`apexretail_quotation_revision_v1:${companyId}:${actor}:${order.id}`;
  const [intent,setIntent]=useState<Intent|null>(null),[reason,setReason]=useState(""),[busy,setBusy]=useState(false),[blocked,setBlocked]=useState(false),[message,setMessage]=useState("");
  const alive=useRef(true),lock=useRef(false);
  useEffect(()=>{alive.current=true;setIntent(null);setBlocked(false);try{const value=JSON.parse(sessionStorage.getItem(key)||"null");if(value&&(!Number.isInteger(value.version)||value.version<1||typeof value.reason!=="string"||!value.reason.trim()||value.reason.length>500||!/^[0-9a-f-]{36}$/i.test(value.request_id)||Object.keys(value).some(k=>!["request_id","version","reason"].includes(k))))throw Error();setIntent(value)}catch{setBlocked(true);setMessage("Retained revision input needs review. Nothing was removed.")}return()=>{alive.current=false}},[key]);
  useEffect(()=>{onPending(!!intent||busy||blocked);return()=>onPending(false)},[intent,busy,blocked,onPending]);
  async function revise(){if(disabled||blocked||!actor||lock.current||!navigator.onLine)return;lock.current=true;setBusy(true);const scope=createBootstrapScope(),token=sessionStorage.getItem("backoffice_token");const current=()=>alive.current&&scope.isCurrent()&&(actorKey!=="backoffice"||(sessionStorage.getItem("backoffice_user_id")===actor&&sessionStorage.getItem("backoffice_token")===token));
    try{const command=intent||{request_id:crypto.randomUUID(),version:order.version,reason};sessionStorage.setItem(key,JSON.stringify(command));setIntent(command);const {data}=await client.post<T>(`/operations/orders/${order.id}/quotation-revision`,command);if(!current())return;
      if(data.kind!=="quotation"||data.id===order.id||data.parent_id!==order.id||data.quotation_command_ack!==command.request_id||data.version<1)throw Error();sessionStorage.removeItem(key);setIntent(null);onChanged(data);
    }catch{if(current())setMessage("Revision not confirmed. Original input retained; retry the same request when connected.")}finally{lock.current=false;if(current())setBusy(false)}
  }
  return <div><p>A revision creates a linked draft. Original terms stay frozen; later sent revisions supersede earlier offers. One lineage can convert once.</p>{message&&<p role="status" aria-live="polite">{message}</p>}{intent?<button type="button" disabled={disabled||busy||blocked||!actor} onClick={()=>void revise()}>Retry original revision</button>:<><label>Revision reason<input maxLength={500} value={reason} onChange={e=>setReason(e.target.value)}/></label><button type="button" disabled={disabled||busy||blocked||!actor||!reason.trim()} onClick={()=>void revise()}>Create linked quotation draft</button></>}</div>;
}
