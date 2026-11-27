/** Approved Backoffice-only settings map; original leaf identifiers remain canonical. */
export type SettingsWorkspace={page:'employees'|'products'|'customers'|'business-operations'|'tip-operations'|'inventory';inventoryTab?:'workflows';workflowTab?:'documents';feature?:'categories'|'units'|'variants'|'price-levels';businessView?:'profile'};
type Entry={title:string;description:string;section?:string;workspace?:SettingsWorkspace};
export const settingsGroups:readonly {id:string;title:string;description:string;entries:readonly Entry[]}[]=[
 {id:'business-branches',title:'Business & Branches',description:'Business identity, shop locations and business profile.',entries:[
  {title:'Company',description:'Existing business identity and contact fields.',section:'company'},
  {title:'Shops',description:'Existing shop addresses, phone and VAT details.',section:'shops'},
  {title:'Business profile',description:'Open existing business profile configuration.',workspace:{page:'business-operations',businessView:'profile'}}]},
 {id:'users-security',title:'Users & Security',description:'Existing employee roles, permissions and account security.',entries:[
  {title:'Employees & permissions',description:'Open existing authorized employee administration.',workspace:{page:'employees'}},
  {title:'Account security',description:'Password recovery, remembered sessions and logout retain their existing secure entry points. This page does not add or weaken security controls.'}]},
 {id:'products-inventory',title:'Products & Inventory',description:'Catalogue configuration; stock workflows stay in Inventory.',entries:[
  {title:'Categories',description:'Existing category administration.',workspace:{page:'products',feature:'categories'}},
  {title:'Units',description:'Existing configured product units.',workspace:{page:'products',feature:'units'}},
  {title:'Variants',description:'Existing variant administration.',workspace:{page:'products',feature:'variants'}},
  {title:'Price levels',description:'Existing configured pricing levels.',workspace:{page:'products',feature:'price-levels'}},
  {title:'Inventory operations',description:'Receiving, returns, transfers, counts and their recovery remain in Inventory. Recipes remain disabled.'}]},
 {id:'sales-checkout',title:'Sales & Checkout',description:'Existing checkout, tax and service-charge policies.',entries:[
  {title:'Receipt, tax & payment policy',description:'Original receipt settings form and values.',section:'receipts'},
  {title:'Tips & Service Charges',description:'Existing tip and service-charge configuration.',section:'tips'},
  {title:'Selling profile',description:'Existing business profile configuration.',workspace:{page:'business-operations',businessView:'profile'}}]},
 {id:'customers-credit',title:'Customers & Credit',description:'Customer-specific configuration; collections remain operational.',entries:[
  {title:'Customer configuration',description:'Existing customer details and credit policy. Collections and settlements remain in their operational menus.',workspace:{page:'customers'}},
  {title:'Credit settings boundary',description:'No new tenant-wide credit policy is invented. Existing customer limits, transaction proofs and payout gates remain authoritative.'}]},
 {id:'payments-currencies',title:'Payments & Currencies',description:'Currency configuration and accepted methods.',entries:[
  {title:'Currencies',description:'Base/accepted currencies and immutable FX history.',section:'currencies'},
  {title:'Accepted payment methods',description:'Original receipt/payment policy form; no provider or split enablement.',section:'receipts'}]},
 {id:'printers-devices',title:'Printers & Devices',description:'Printer configuration, routing and terminal administration.',entries:[
  {title:'Printers & kitchen',description:'Existing stations, routing and print recovery.',section:'printers'},
  {title:'Devices/POS',description:'Existing terminal assignments and device security.',section:'devices'}]},
 {id:'documents-branding',title:'Documents & Branding',description:'Receipt configuration and existing document settings.',entries:[
  {title:'Receipts',description:'Existing receipt text and paper settings.',section:'receipts'},
  {title:'Templates & private media',description:'Open the existing Inventory document workspace for template/logo configuration and retained request recovery. Rendering and delivery remain there as operational workflows.',workspace:{page:'inventory',inventoryTab:'workflows',workflowTab:'documents'}},
  {title:'Fiscal draft settings',description:'Existing draft mappings and commissioning status; no fiscal confirmation.',section:'fiscal'}]},
 {id:'appearance-navigation',title:'Appearance & Navigation',description:'Scoped shared-tool and Backoffice workspace presentation.',entries:[
  {title:'Presentation',description:'Company, branch and device preferences; historical acknowledgements retained.',section:'presentation'}]},
 {id:'subscriptions-integrations',title:'Subscriptions & Integrations',description:'Existing subscription and integration commissioning settings.',entries:[
  {title:'Subscription',description:'Existing status and renewal configuration, retaining provider gates.',section:'subscription'},
  {title:'Fiscalisation',description:'Existing fiscal draft/provider commissioning settings.',section:'fiscal'},
  {title:'Integration boundary',description:'No new live provider connection, credential, message, payment or fiscal action is enabled by this navigation map.'}]},
];
export function settingsGroup(id:string|null){return settingsGroups.find(group=>group.id===id)||null}
export function filteredSettingsGroups(search:string){const query=search.trim().toLowerCase();return settingsGroups.filter(group=>`${group.title} ${group.description} ${group.entries.map(entry=>entry.title+' '+entry.description).join(' ')}`.toLowerCase().includes(query))}
