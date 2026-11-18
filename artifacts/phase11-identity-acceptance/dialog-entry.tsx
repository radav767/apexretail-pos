import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import Dialog from '../src/components/BackofficeHandoffDialog';
function Test() {
 const [open, setOpen] = useState(false);
 return <><button onClick={() => setOpen(true)}>Test owner authentication</button><Dialog open={open} onClose={() => setOpen(false)} authenticate={async (email,password) => {
  const fixture = (window as any).__fixture;
  const response = await fetch('https://api.apexpos.cloud/api/auth/handoff', {method:'POST', headers:{'Content-Type':'application/json',Authorization:'Bearer '+fixture.employee},body:JSON.stringify({company_id:fixture.company,branch_id:fixture.branch,owner_email:email,owner_password:password})});
  if (!response.ok) return false;
  (window as any).__handoff = (await response.json()).url;
  return true;
 }}/></>;
}
createRoot(document.getElementById('root')!).render(<Test/>);
