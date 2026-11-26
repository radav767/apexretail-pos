import {canOpenSalesDestination,salesDestinations,type NavigationActor} from './salesReports';
/** POS is a selling surface. Administrative routes are recovery-compatible gateways. */
export function dailyPosDestinations(actor:NavigationActor|null){
 return salesDestinations.filter(item=>['history','returns','shift','z'].includes(item.id)&&canOpenSalesDestination(actor,item.id));
}
export function isDailyPosRoute(module:string,feature:string){
 return module==='Sales'||module==='Business Operations'||module==='Shift Management'||
  module==='Sales Management'&&['home','transaction-history','cancel-void-sales','cashier-shifts','z-reports','request-recovery'].includes(feature)||
  module==='Inventory'&&['home','inventory-overview'].includes(feature)||
  module==='Settings'&&['home','printer'].includes(feature);
}

export function canLookupStock(actor:NavigationActor|null){
 if(!actor)return false;const p=actor.permissions||{};
 return ['owner','administrator','manager'].includes(actor.role||'')||['sales','manage_products','manage_inventory'].some(key=>p[key]===true);
}
