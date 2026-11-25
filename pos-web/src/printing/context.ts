import {createBootstrapScope} from '../api/authLifecycle';
let generation=0;
if(typeof window!=='undefined')window.addEventListener('business-context-changed',()=>{generation++});
/** A delayed print must retain its original user and register, including same-user reassignment. */
export function createPrintScope() {
  const auth=createBootstrapScope(),keys=['device_id','branch_id','shop_id'] as const;
  const values=keys.map(key=>localStorage.getItem(key)),epoch=generation;
  const businessKeys=['backoffice_token','backoffice_company_id','backoffice_user_id'];
  const business=businessKeys.map(key=>typeof sessionStorage==='undefined'?null:sessionStorage.getItem(key));
  return {isCurrent:()=>epoch===generation&&auth.isCurrent()&&keys.every((key,index)=>localStorage.getItem(key)===values[index])&&businessKeys.every((key,index)=>(typeof sessionStorage==='undefined'?null:sessionStorage.getItem(key))===business[index])};
}
