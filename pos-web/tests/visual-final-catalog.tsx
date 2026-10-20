import { createRoot } from "react-dom/client";
import { AxiosError } from "axios";
import ProductToolsPage, { type ProductToolFeature } from "../src/ProductToolsPage";
import ProductsPage from "../../backoffice/src/pages/ProductsPage";
import BatchStockPanel from "../src/business/BatchStockPanel";
import PosModulePage from "../src/PosModulePage";
import FocusedOperationsPage from "../src/FocusedOperationsPage";
import BranchTransferPanel from "../../backoffice/src/pages/BranchTransferPanel";
import StockTakePanel from "../../backoffice/src/pages/StockTakePanel";
import { api } from "../src/api/client";
import { api as backofficeApi } from "../../backoffice/src/api/client";
import { canManageProductTool, catalogPermission } from "../src/catalogAccess";
import "../src/index.css";
import "../src/pos-modules.css";
import "../src/premium-theme.css";
import "../../backoffice/src/pages/inventory.css";

const query = new URLSearchParams(location.search);
const feature = query.get("feature") || "categories";
const permitted = query.get("restricted") !== "true";
const costs = query.get("costs") !== "false";
const requests: { method: string; url: string; payload: Record<string, unknown> }[] = [];
Object.assign(window, { catalogRequests: requests, catalogAccess: { canManageProductTool, catalogPermission } });
const products = [{id:"product",name:"Synthetic stock item",sku:"SYN-1",product_type:"standard",unit:"each",track_inventory:true,
  cost_price:costs ? "2" : null,selling_price:"5",stock_qty:"100",reorder_level:"2",active:true,units_per_purchase:"1"}];
let categories = [{id:"category",name:"Existing category",parent_id:null,image_url:null,active:true}];
let variants: Record<string, unknown>[] = [{id:"variant",name:"Small",sku:"SIZE-S",barcode:"123456",attributes:{size:"S"},cost_price:costs ? "2" : null,selling_price:"5",stock_qty:"8",reorder_level:"2",active:true}];
let prices: Record<string, unknown>[] = [{id:"price",name:"Wholesale",price:"4",minimum_quantity:"12",active:true}];
let transferAttempts=0;
const adapter: typeof api.defaults.adapter = async config => {
  const url = config.url || ""; const method = config.method || "get";
  const payload = typeof config.data === "string" ? JSON.parse(config.data) : config.data || {};
  requests.push({method,url,payload});
  let data: unknown = [];
  if(url==="/inventory/transfers/capabilities") {
    if(query.get("legacy")==="true")throw new AxiosError("Not found","ERR_BAD_REQUEST",config,undefined,{data:{detail:"Not found"},status:404,statusText:"Not found",headers:{},config});
    data={idempotency:"audit-v1",variant_transfers:true};
  } else if(url==="/inventory/transfers") {
    if(transferAttempts++===0)throw new AxiosError("Network Error","ERR_NETWORK",config);
    data=[{id:"source-movement"},{id:"destination-movement"}];
  }
  else if(url==="/inventory/stock-take/capabilities")data={idempotency:"audit-v1",variant_counts:true,expected_quantity:true};
  else if(url.includes("/inventory/count-catalog/"))data=[{key:"variant",product_id:"product",variant_id:"variant",name:"Synthetic stock item — Small",sku:"SIZE-S",unit:"each",stock_qty:"8",active:true,batches:[]}];
  else if(url==="/inventory/stock-take") {
    if(transferAttempts++===0)throw new AxiosError("Network Error","ERR_NETWORK",config);
    data=[{id:"count-movement"}];
  }
  else if (url.includes("/inventory/branches/")||url.includes("/inventory/transfer-destinations/")) data=[{id:"branch",name:"Synthetic branch",shop_name:"Synthetic shop"},{id:"destination",name:"Destination",shop_name:"Synthetic shop"}];
  else if(url.includes("/inventory/overview/") || url.includes("/inventory/branch-overview/"))data=[{product_id:"product",name:"Synthetic stock item",quantity:"100",unit:"each"}];
  else if (url.includes("/products/categories")) {
    if(method==="post") {const row={id:"created",active:true,...payload};categories.push(row);data=row;}
    else if(method==="patch") {categories=categories.map(row=>row.id===url.split("/").at(-1)?{...row,...payload}:row);data=categories.find(row=>row.id===url.split("/").at(-1));}
    else if(method==="delete") {
      if(url.endsWith("/category")) throw new AxiosError("Conflict","ERR_BAD_REQUEST",config,undefined,{data:{detail:"Category contains products"},status:409,statusText:"Conflict",headers:{},config});
      categories=categories.filter(row=>row.id!==url.split("/").at(-1));data={ok:true};
    } else data=categories;
  } else if(url.includes("/products/variants/")) {
    if(method==="post") {data={id:"created-variant",active:true,...payload};variants.push(data as Record<string,unknown>);}
    else if(method==="patch") {variants=variants.map(row=>row.id===url.split("/").at(-1)?{...row,...payload}:row);data=variants.find(row=>row.id===url.split("/").at(-1));}
    else data=feature==="transfers"&&query.get("variant")!=="true"?[]:variants;
  } else if(url.includes("/products/price-levels/")) {
    if(method==="post") {data={id:"created-price",active:true,...payload};prices.push(data as Record<string,unknown>);}
    else if(method==="patch") {prices=prices.map(row=>row.id===url.split("/").at(-1)?{...row,...payload}:row);data=prices.find(row=>row.id===url.split("/").at(-1));}
    else if(method==="delete") {prices=prices.filter(row=>row.id!==url.split("/").at(-1));data={ok:true};}
    else data=prices;
  } else if(url==="/products" && method==="post") {
    data={...products[0],...payload,id:"created-product"};products.push(data as typeof products[number]);
  } else if(url.includes("/products/") && method==="patch") {
    const item=products.find(row=>row.id===url.split("/").at(-1));Object.assign(item || {},payload);data=item;
  } else if(url.includes("/products/") && method==="delete") {
    const item=products.find(row=>row.id===url.split("/").at(-1));if(item)item.active=false;data={ok:true};
  } else if(url.includes("/products/")) data=products;
  return {data:structuredClone(data),status:200,statusText:"OK",headers:{},config};
};
api.defaults.adapter=adapter;backofficeApi.defaults.adapter=adapter;
let countAttempts=0;
const moduleProps={activeModule:"Products",companyId:"fixture-company",branchId:"branch",shiftStatus:"open",currencySymbol:"$",decimalPlaces:2,
  cashier:{id:"employee",name:"Synthetic staff",role:"custom",permissions:{manage_products:true,products_add:permitted,products_edit:permitted,products_delete:permitted,product_costs_view:costs}},
  printerConfig:{enabled:false,connectionType:"system",paperWidth:"80mm",copies:1},printerConfigLoaded:false,
  bluetoothPrinters:[],usbPrinters:[],onBackToSales:()=>undefined,
} as Parameters<typeof PosModulePage>[0];
createRoot(document.getElementById("root")!).render(feature==="batch-count"
  ? <BatchStockPanel identity="synthetic-count" branch="branch" products={products} receive={false} adjust={false} count online
      send={async payload=>{
        requests.push({method:"post",url:"/operations/batches/stock",payload:payload as Record<string,unknown>});
        if(countAttempts++===0) throw new Error("Synthetic timeout");
        return {movement_id:"synthetic-movement",batch_id:"synthetic-batch"};
      }} changed={async()=>undefined}/>
  : feature==="stock-count" ? <StockTakePanel companyId="fixture-company" branchId="branch" client={api} identity={`synthetic-${query.get("app")}`} />
  : feature==="transfers" ? query.get("app")==="backoffice"
    ? <BranchTransferPanel companyId={query.get("variant")==="true"?"fixture-company-variant":"fixture-company"} />
    : <FocusedOperationsPage feature="stock-transfers" companyId={query.get("variant")==="true"?"fixture-company-variant":"fixture-company"} branchId="branch" identity="synthetic-employee" permitted />
  : query.get("app")==="module" ? <PosModulePage {...moduleProps} />
  : query.get("app")==="backoffice"
  ? <ProductsPage companyId="fixture-company" />
  : <ProductToolsPage feature={feature as ProductToolFeature} companyId="fixture-company" branchId="branch" canManage={permitted} canViewCosts={costs} />);
