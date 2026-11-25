import { splitPaymentRows } from './splitReceipt';
import type { SplitAccounting } from './splitReceipt';
export default function AllocationDetails({accounting,total,method}:{accounting?:SplitAccounting|null;total:string;method:string}) {
  if (!['split','split_refund'].includes(method)) return null;
  return <dl aria-label="Recorded split allocations">{splitPaymentRows(accounting,total,method).map(([label,value],index)=><div key={index} style={{display:'grid',gridTemplateColumns:'minmax(0,1fr) minmax(0,1fr)',gap:8,padding:4}}><dt>{label}</dt><dd style={{margin:0,overflowWrap:'anywhere'}}>{value}</dd></div>)}</dl>;
}
