import {useEffect,useState} from 'react';
import {createPrintScope} from '../printing/context';
export type WorkspaceView='tiles'|'list';
export type WorkspaceTextSize='standard'|'large';
export type WorkspaceValues={backoffice_workspace_view?:WorkspaceView;backoffice_text_size?:WorkspaceTextSize};
export const WORKSPACE_CONTRACT='backoffice-workspace-preferences-v3';
export function workspaceValues(values:WorkspaceValues|undefined){
 return {backoffice_workspace_view:values?.backoffice_workspace_view==='list'?'list':'tiles',backoffice_text_size:values?.backoffice_text_size==='large'?'large':'standard'} as const;
}
type Client={get:<T>(path:string,config:any)=>Promise<{data:T}>};
/** Backoffice hub is company scoped: no invented global branch/device selection. */
export function useBackofficeWorkspace(companyId:string,client?:Client){
 const [saved,setSaved]=useState<{company:string;values:WorkspaceValues}|null>(null),[epoch,setEpoch]=useState(0);
 useEffect(()=>{const changed=()=>setEpoch(n=>n+1);window.addEventListener('selector-preferences-changed',changed);window.addEventListener('business-context-changed',changed);return()=>{window.removeEventListener('selector-preferences-changed',changed);window.removeEventListener('business-context-changed',changed)}},[]);
 useEffect(()=>{const abort=new AbortController(),identity=createPrintScope();setSaved(null);
  if(companyId&&client)void client.get<{effective:WorkspaceValues}>(`/settings/preferences/${companyId}`,{signal:abort.signal}).then(({data})=>{if(!abort.signal.aborted&&identity.isCurrent())setSaved({company:companyId,values:workspaceValues(data.effective)})}).catch(()=>{});
  return()=>abort.abort();
 },[companyId,client,epoch]);
 return workspaceValues(saved?.company===companyId?saved.values:undefined);
}
