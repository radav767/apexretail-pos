// Test entry only. No production entry imports this synthetic adapter.
import { createRoot } from "react-dom/client";
import FocusedOperationsPage,{type FocusedFeature} from "../../pos-web/src/FocusedOperationsPage";
import BatchValuationPanel from "../../pos-web/src/business/BatchValuationPanel";
import {api} from "../../pos-web/src/api/client";
const params=new URL(location.href).searchParams;const feature=(params.get("feature")||"stock-transfers") as FocusedFeature;
const calls:unknown[]=[];
api.defaults.adapter=async config=>{
  const url=config.url||"";const body=typeof config.data==="string"?JSON.parse(config.data):config.data;
  calls.push({url,method:config.method,body,params:config.params});let data:unknown;
  if(url.startsWith("/inventory/branches"))data=[{id:"source",name:"Main",shop_name:"Synthetic shop"},{id:"destination",name:"Store room",shop_name:"Synthetic shop"}];
  else if(url.startsWith("/inventory/branch-overview"))data=[{product_id:"product",product_name:"Synthetic stock",quantity:"20"}];
  else if(url==="/inventory/transfers"){
    const receipt=[{id:"movement-out",product_id:"product",branch_id:"source",quantity:body.items[0].quantity,movement_type:"transfer_out",reference:body.reference},{id:"movement-in"}];
    localStorage.setItem("synthetic-transfer-receipt",JSON.stringify(receipt));
    if(params.has("timeout"))throw new Error("Synthetic response lost after commit");data=receipt;
  }else if(url.startsWith("/inventory/history")){
    if(config.params?.limit!==500)throw new Error("History API contract requires the approved maximum of 500");
    data=JSON.parse(localStorage.getItem("synthetic-transfer-receipt")||"[]");
  }
  else if(url.endsWith("export.csv"))data=new Blob(["label,quantity,amount\nSynthetic stock,3,36.00"],{type:"text/csv"});
  else if(url.startsWith("/reports/sales-history"))data={currency_symbol:"$",rows:[{label:config.params?.view==="product"?"Synthetic stock":"SYN-0042",quantity:"3",amount:"36.00"}]};
  else if(url.startsWith("/reports/batch-valuation"))data={basis:"Current variant unit costs; attribution, not additional stock.",currency_symbol:"$",rows:[{batch_id:"lot-a",product_name:"Synthetic medicine",variant_name:"250mg",code:"LOT-A",quantity:"10",expires_on:"2027-06-30",unit_cost:"4.00",cost_value:"40.00"},{batch_id:"lot-b",product_name:"Synthetic medicine",variant_name:"500mg",code:"LOT-B",quantity:"8",expires_on:"2027-06-30",unit_cost:"6.00",cost_value:"48.00"}]};
  else throw new Error(`Unexpected synthetic route ${url}`);
  return{data,status:200,statusText:"OK",headers:{},config};
};
Object.assign(window,{__completionCalls:calls});
createRoot(document.getElementById("root")!).render(<main style={{fontFamily:"system-ui",padding:12,background:"#f5f7f8",minHeight:"100vh",color:"#20252b"}}><header style={{padding:16,borderRadius:12,background:"#07583b",color:"white"}}><strong>ApexRetail · Completion review</strong><p>Synthetic data · Not production</p></header>{feature as string==="batches"?<section className="business-operations"><BatchValuationPanel company="synthetic-company" branch="source" api={api}/></section>:<FocusedOperationsPage feature={feature} companyId="synthetic-company" branchId="source" identity="synthetic-cashier:register" permitted={!params.has("denied")}/>}</main>);
