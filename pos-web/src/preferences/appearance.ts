import {useEffect,useState} from 'react';
import {createPrintScope} from '../printing/context';
import './shared-tool-theme.css';
export type ToolScheme='light'|'dark'|'system';
export type ToolTheme='light'|'dark';
export function validToolScheme(value:unknown):ToolScheme|null{
 return value==='light'||value==='dark'||value==='system'?value:null;
}
/** Read-only browser signal. It never persists or changes operational settings. */
export function useResolvedToolTheme(scheme:ToolScheme):ToolTheme{
 const [dark,setDark]=useState(()=>typeof matchMedia==='function'&&matchMedia('(prefers-color-scheme: dark)').matches);
 useEffect(()=>{if(typeof matchMedia!=='function')return;const media=matchMedia('(prefers-color-scheme: dark)'),changed=()=>setDark(media.matches);changed();media.addEventListener('change',changed);return()=>media.removeEventListener('change',changed)},[]);
 return scheme==='system'?(dark?'dark':'light'):scheme;
}

type Client={get:<T>(path:string,config:{params:Record<string,string>;signal:AbortSignal})=>Promise<{data:T}>};
/** Scope metadata follows the same current identity checks as other shared tools. */
export function useToolAppearance(companyId:string,branchId:string,scopeKey:string,client:Client){
 const [saved,setSaved]=useState<{scope:string;scheme:ToolScheme}|null>(null),[epoch,setEpoch]=useState(0);
 const scope=JSON.stringify([companyId,branchId,scopeKey]);
 useEffect(()=>{const changed=()=>setEpoch(n=>n+1);window.addEventListener('selector-preferences-changed',changed);window.addEventListener('business-context-changed',changed);return()=>{window.removeEventListener('selector-preferences-changed',changed);window.removeEventListener('business-context-changed',changed)}},[]);
 useEffect(()=>{
  const controller=new AbortController(),identity=createPrintScope();setSaved(null);
  if(companyId){const device=branchId&&localStorage.getItem('branch_id')===branchId&&!sessionStorage.getItem('backoffice_user_id')?localStorage.getItem('device_id'):null;
   void client.get<{effective:{tool_color_scheme?:unknown}}>(`/settings/preferences/${companyId}`,{params:{...(branchId?{branch_id:branchId}:{}),...(device?{device_id:device}:{})},signal:controller.signal}).then(({data})=>{
    const scheme=validToolScheme(data.effective?.tool_color_scheme);if(!controller.signal.aborted&&identity.isCurrent()&&scheme)setSaved({scope,scheme});
   }).catch(()=>{});
  }
  return()=>controller.abort();
 },[companyId,branchId,scopeKey,client,scope,epoch]);
 return useResolvedToolTheme(saved?.scope===scope?saved.scheme:'light');
}
