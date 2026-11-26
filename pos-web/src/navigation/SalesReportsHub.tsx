import {salesDestinations,canOpenSalesDestination,type NavigationActor,type SalesDestination} from './salesReports';
import '../components/sales-reports-hub.css';
export default function SalesReportsHub({actor=null,onSelect,backoffice=false}:{actor?:NavigationActor|null;onSelect:(item:SalesDestination)=>void;backoffice?:boolean}){
 const destinations=salesDestinations.filter(item=>(backoffice||canOpenSalesDestination(actor,item.id))&&(!backoffice||!['returns','z','top','inventory','reconciliation'].includes(item.id)));
 return <section className="sales-reports-hub" aria-label="Sales & Reports"><h2>Sales &amp; Reports</h2><p>Open a workspace to review its records or continue a saved request.</p>
  <div className="sales-reports-tiles">{destinations.map(item=><button type="button" key={item.id} onClick={()=>onSelect(item)}><strong>{backoffice&&item.id==='history'?'Sales History':item.title}</strong><span>{item.detail}</span></button>)}</div>
  <p>Saved requests remain in Transaction History, Shift Management, Business Operations, Inventory and document settings. Opening this hub does not resend them.</p>
 </section>
}
