import type {PosModuleName} from '../PosModulePage';
export type NavigationActor={role?:string|null;permissions?:Record<string,boolean>};
export type SalesDestination={id:string;title:string;detail:string;module:PosModuleName;feature?:string;page?:string};
export const salesDestinations:readonly SalesDestination[]=[
 {id:'history',title:'Transaction History',detail:'Completed sales, receipts and saved refund requests',module:'Sales Management',feature:'transaction-history',page:'sales'},
 {id:'returns',title:'Cancel / Void Sales',detail:'Receipt review and authorized returns',module:'Sales Management',feature:'cancel-void-sales',page:'sales'},
 {id:'shift',title:'Shift Management',detail:'Current shift, own history and request recovery',module:'Shift Management',page:'shift-reports'},
 {id:'z',title:'Z Reports',detail:'Immutable shift reports and output',module:'Sales Management',feature:'z-reports',page:'shift-reports'},
 {id:'customers',title:'Customers',detail:'Customer accounts and existing balances',module:'Customers',page:'customers'},
 {id:'credit',title:'Credit Settlement',detail:'Recorded collections and debt reconciliation',module:'Credit Settlements',page:'credit-settlements'},
 {id:'expenses',title:'Expenses',detail:'Authorized expenses and reports',module:'Expenses',page:'expenses'},
 {id:'tips',title:'Tip operations & recovery',detail:'Existing tip reports and retained request review',module:'Reports',feature:'tip-operations',page:'tip-operations'},
 {id:'summary',title:'Sales Summary',detail:'Recorded sales overview',module:'Reports',feature:'sales-summary',page:'dashboard'},
 {id:'reports',title:'Sales Reports',detail:'Filtered sales reports and historical values',module:'Reports',feature:'sales-reports',page:'reports'},
 {id:'top',title:'Top Selling Products',detail:'Product performance reports',module:'Reports',feature:'top-products',page:'reports'},
 {id:'inventory',title:'Inventory Status',detail:'Product and low-stock overview',module:'Reports',feature:'inventory-status',page:'inventory'},
 {id:'reconciliation',title:'Reconciliation Export',detail:'Read-only revenue, payments, debt, tax and FX snapshot',module:'Reports',feature:'reconciliation',page:'reports'},
];
export function canOpenSalesDestination(actor:NavigationActor|null|undefined,id:string):boolean{
 if(!actor)return false;
 if(actor.role==='owner'||actor.role==='administrator')return salesDestinations.some(item=>item.id===id);
 const p=actor.permissions||{},history=(p.sales_history_view??p.sales)===true;
 switch(id){
  case 'history':case 'returns':return history;
  case 'shift':return true; // Own recovery reads retain server enforcement for every action.
  case 'z':return p.z_reports_view===true;
  case 'tips':return p.tips_reports_view===true;
  case 'customers':return p.customers_view===true;
  case 'credit':return p.credit_settlements===true;
  case 'expenses':return p.expenses_create===true||p.expense_reports===true;
  case 'summary':case 'inventory':return p.revenue_view===true;
  case 'reports':case 'top':return p.profits_view===true;
  case 'reconciliation':return p.revenue_view===true&&p.credit_settlements===true;
  default:return false;
 }
}
export function salesDestinationFor(module:PosModuleName,feature:string){
 if(module==='Sales Management'&&feature==='cashier-shifts')return salesDestinations.find(item=>item.id==='shift');
 if(module==='Sales Management'&&feature==='credit-settlement')return salesDestinations.find(item=>item.id==='credit');
 return salesDestinations.find(item=>item.module===module&&(item.feature||'home')===feature);
}
