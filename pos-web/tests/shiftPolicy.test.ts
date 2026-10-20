import assert from "node:assert/strict";
import { hasActiveCashierShift, saleShiftError } from "../src/shiftPolicy.js";
const identity = { company_id:"company",branch_id:"branch",employee_id:"cashier-A",device_id:"register" };
const shift = {...identity,id:"shift",status:"open",offline_shift_token:"signed-original-identity"};
let checks=0;
function check(condition:unknown){assert.ok(condition);checks++;}
check(hasActiveCashierShift(shift,identity));
check(saleShiftError(true,shift,identity)===null);
check(saleShiftError(true,shift,identity,true)===null);
check(saleShiftError(false,null,identity)===null);
check(saleShiftError(false,null,identity,true)===null);
check(saleShiftError(true,null,identity)?.includes("Start Shift"));
check(saleShiftError(true,{...shift,status:"closed"},identity)?.includes("Start Shift"));
check(saleShiftError(true,{...shift,offline_shift_token:null},identity,true)?.includes("Reconnect"));
for(const field of Object.keys(identity) as Array<keyof typeof identity>){
  check(!hasActiveCashierShift({...shift,[field]:"another"},identity));
  check(saleShiftError(true,shift,{...identity,[field]:""})!==null);
}
console.log(`${checks} shift policy assertions passed (online/offline/identity/legacy)`);
