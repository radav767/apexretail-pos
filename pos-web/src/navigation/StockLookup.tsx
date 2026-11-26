import {useEffect,useState} from 'react';
import {api} from '../api/client';
import ProductSelector,{type SelectionProduct} from '../components/ProductSelector';
export default function StockLookup({company,branch,identity}:{company:string;branch:string;identity:string}){
 const [selected,setSelected]=useState<SelectionProduct|null>(null);
 useEffect(()=>setSelected(null),[company,branch,identity]);
 return <section aria-label="Stock lookup"><h2>Stock lookup</h2><p>Search products and available branch stock.</p><ProductSelector companyId={company} branchId={branch} scopeKey={identity} value={selected?.id||''} onChange={(_,product)=>setSelected(product)} client={api}/>
 {selected&&<p role="status">{selected.name}: {selected.branch_stock_qty??'Not tracked'} {selected.unit}</p>}</section>
}
