import {readFileSync,writeFileSync} from 'node:fs';
import {join,extname,resolve} from 'node:path';
import assert from 'node:assert/strict';
import {chromium} from '/tmp/apex-phase11-browser-tools/node_modules/playwright/index.mjs';
const API='http://127.0.0.1:18128/api',POS='https://pos.synthetic.invalid',BO='https://backoffice.synthetic.invalid';
async function request(path,body,token,method='POST') {
 const r=await fetch(API+path,{method,headers:{'Content-Type':'application/json',...(token?{Authorization:'Bearer '+token}:{})},...(body?{body:JSON.stringify(body)}:{})});
 const text=await r.text();assert.ok(r.ok,`${path}: ${r.status} ${text}`);return JSON.parse(text);
}
const password='Synthetic-Shell-Only-123!';
const tenant=await request('/auth/register',{owner_name:'Synthetic shell owner',owner_pin:'1234',business_name:'Synthetic shell receipts',business_type:'Retail',country:'Zimbabwe',phone:'000000000',email:`shell-${crypto.randomUUID()}@example.com`,password,confirm_password:password,base_currency_code:'USD',base_currency_symbol:'$',base_currency_decimal_places:2});
const C=tenant.company.id,B=tenant.branch.id,D=tenant.device.id,T=tenant.token;
const product=await request('/products',{company_id:C,branch_id:B,name:'Synthetic shell product',selling_price:'12',cost_price:'2',stock_qty:'100',create_request_key:crypto.randomUUID()},T);
const sale=await request('/sales',{company_id:C,branch_id:B,device_id:D,assignment_revision:tenant.device.assignment_revision||1,client_sale_id:crypto.randomUUID(),payment_method:'cash',amount_received:'20',items:[{product_id:product.id,quantity:'1'}]},T);
writeFileSync('/tmp/phase11-shell-seed.json',JSON.stringify({tenant,password,product,sale},null,2)); // disposable credentials; never commit.
const browser=await chromium.launch({executablePath:'/root/.cache/ms-playwright/chromium_headless_shell-1243/chrome-headless-shell-linux64/chrome-headless-shell',headless:true,args:['--no-sandbox','--disable-background-networking']});
const errors=[],unexpected=[];let fault=null;const faults=[];const waitFor=async predicate=>{for(let i=0;i<200;i++){if(predicate())return;await new Promise(r=>setTimeout(r,50))}throw Error('Timed out waiting for controlled real response')};
try {
 const context=await browser.newContext({viewport:{width:1440,height:1100}});await context.addInitScript(()=>{window.print=()=>{throw Error('No print transport permitted in acceptance')}});
 await context.route('**/*',async route=>{
  const req=route.request(),u=new URL(req.url());if(![POS,BO].includes(u.origin)){unexpected.push(u.origin);return route.abort()}
  if(u.pathname.startsWith('/api/')) {const headers={...req.headers(),origin:u.origin};delete headers.host;const r=await route.fetch({url:'http://127.0.0.1:18128'+u.pathname+u.search,headers});if(r.status()>=400&&!u.pathname.includes('/auth/refresh'))console.log('HTTP',u.pathname,r.status());if(fault&&fault.matches(u,req)){const f=fault;fault=null;f.status=r.status();f.body=await r.body();f.request=req.postData();f.seen=true;faults.push(f);if(f.mode==='drop')return route.abort();await new Promise(resolve=>f.release=resolve)}return route.fulfill({response:r})}
  const root=`/tmp/apex-phase11-build-xijhpj7t/${u.origin===POS?'pos-web':'backoffice'}/dist`,path=resolve(root,'.'+u.pathname);
  assert.ok(path.startsWith(root));let data;try{data=readFileSync(path)}catch{data=readFileSync(join(root,'index.html'))}
  const type={'.js':'text/javascript','.css':'text/css','.json':'application/json','.svg':'image/svg+xml','.png':'image/png','.wasm':'application/wasm'}[extname(path)]||'text/html';return route.fulfill({body:data,contentType:type});
 });
 const page=await context.newPage();page.on('pageerror',e=>errors.push(String(e)));
 await page.goto(POS);await page.waitForTimeout(1000);
 await page.locator('input[type=email]').fill(tenant.user.email);await page.locator('input[type=password]').fill(password);await page.getByRole('button',{name:'Sign in',exact:true}).last().click();await page.waitForTimeout(1500);await page.locator('input').filter({visible:true}).first().fill('1234');await page.getByRole('button',{name:'Open POS',exact:true}).click();await page.waitForTimeout(1500);await page.getByLabel('Opening cash · USD').fill('20');await page.getByRole('button',{name:'OPEN SHIFT',exact:true}).click();await page.waitForTimeout(800);if(await page.getByRole('button',{name:'Return to Sales',exact:true}).count())await page.getByRole('button',{name:'Return to Sales',exact:true}).click();await page.waitForTimeout(800);await page.getByRole('button',{name:'Transaction History',exact:true}).click();await page.waitForTimeout(800);
 const auth=await page.evaluate(()=>({token:localStorage.getItem('employee_token'),device:localStorage.getItem('device_id')}));
 const customer=await request('/customers',{company_id:C,customer_code:'SHELL',name:'Synthetic receipt debtor',credit_enabled:true,unlimited_credit:false,credit_limit:'100'},T);
 const shift=await request('/shifts/current',null,auth.token,'GET');
 const body={contract_version:'split-v2',company_id:C,branch_id:B,device_id:auth.device,assignment_revision:1,currency_config_version:1,client_sale_id:crypto.randomUUID(),shift_id:shift.id,customer_id:customer.id,expected_total:'12',items:[{product_id:product.id,quantity:'1'}],tenders:[{id:crypto.randomUUID(),method:'cash',currency_code:'USD',applied_original:'8',tendered_original:'10',applied_base:'8',exchange_rate_snapshot:'1'},{id:crypto.randomUUID(),method:'credit',currency_code:'USD',applied_original:'4',applied_base:'4',exchange_rate_snapshot:'1'}]};
 const mixed=await request('/sales/v2/split',body,auth.token);assert.equal((await request('/sales/v2/split',body,auth.token)).sale.id,mixed.sale.id);
 const original=await request(`/sales/receipt/${C}/${mixed.sale.id}?mark_reprint=false`,null,auth.token,'GET');
 const credit=mixed.tenders.find(r=>r.method==='credit'),cash=mixed.tenders.find(r=>r.method==='cash');
 const refundBody={contract_version:'split-refund-v2',request_id:crypto.randomUUID(),company_id:C,branch_id:B,device_id:auth.device,assignment_revision:1,shift_id:shift.id,original_sale_id:mixed.sale.id,reason:'Synthetic shell partial return',expected_total:'6',items:[{sale_item_id:original.items[0].id,quantity:'.5'}],allocations:[{tender_id:credit.id,kind:'debt_reduction',amount_base:'4',amount_original:'4'},{tender_id:cash.id,kind:'paid_refund',amount_base:'2',amount_original:'2'}]};
 const returned=await request('/sales/v2/split/refunds',refundBody,auth.token);assert.equal((await request('/sales/v2/split/refunds',refundBody,auth.token)).sale.id,returned.sale.id);
 await page.getByRole('button',{name:'Sales',exact:true}).click();await page.getByRole('button',{name:'Transaction History',exact:true}).click();
 const originalRow=page.getByRole('row').filter({hasText:mixed.sale.receipt_number});await originalRow.getByRole('button',{name:'View Receipt',exact:true}).click();await page.getByRole('dialog').getByText('Original unpaid credit',{exact:true}).waitFor();await page.getByRole('button',{name:'Close receipt',exact:true}).click();
 await page.getByRole('row').filter({hasText:returned.sale.receipt_number}).getByRole('button',{name:'View Receipt',exact:true}).click();await page.getByRole('dialog').getByText('Debt reduction',{exact:true}).waitFor();await page.getByRole('button',{name:'Close receipt',exact:true}).click();
 console.log('POS actual navigation/auth/persisted original and refund receipts passed');
 writeFileSync('/tmp/phase11-shell-records.json',JSON.stringify({company:C,product:product.id,original:mixed.sale.id,refund:returned.sale.id},null,2));
 
 writeFileSync('/tmp/phase11-shell-dom.html',await page.content());
 const backoffice=await context.newPage();backoffice.on('pageerror',e=>errors.push(String(e)));await backoffice.goto(BO);await backoffice.waitForTimeout(1000);await backoffice.locator('input[type=email]').fill(tenant.user.email);await backoffice.locator('input[type=password]').fill(password);await backoffice.getByRole('button',{name:'Login',exact:true}).click();await backoffice.waitForTimeout(1500);
 await backoffice.getByRole('button',{name:'Sales History',exact:true}).first().click();await backoffice.getByRole('row').filter({hasText:mixed.sale.receipt_number}).getByRole('button',{name:'View receipt',exact:true}).click();await backoffice.getByRole('dialog').getByText('Original unpaid credit',{exact:true}).waitFor();await backoffice.getByRole('button',{name:'Close receipt',exact:true}).click();
 await backoffice.getByRole('row').filter({hasText:returned.sale.receipt_number}).getByRole('button',{name:'View receipt',exact:true}).click();await backoffice.getByRole('dialog').getByText('Debt reduction',{exact:true}).waitFor();await backoffice.getByRole('button',{name:'Close receipt',exact:true}).click();
 console.log('Backoffice actual navigation/auth/persisted original and refund receipts passed');
 const stale={mode:'hold',matches:u=>u.pathname===`/api/sales/receipt/${C}/${mixed.sale.id}`};fault=stale;
 await backoffice.getByRole('row').filter({hasText:mixed.sale.receipt_number}).getByRole('button',{name:'View receipt',exact:true}).click();await waitFor(()=>stale.release);
 await backoffice.getByRole('button',{name:'Log out',exact:true}).first().click();await backoffice.getByRole('button',{name:'Login',exact:true}).waitFor();stale.release();await backoffice.waitForTimeout(200);assert.equal(await backoffice.getByRole('dialog').count(),0);
 console.log('Backoffice lost identity rejects delayed receipt response');

 const loginBO=async p=>{await p.locator('input[type=email]').fill(tenant.user.email);await p.locator('input[type=password]').fill(password);await p.getByRole('button',{name:'Login',exact:true}).click();await p.getByRole('button',{name:'Log out',exact:true}).first().waitFor()};
 const documents=async p=>{await p.getByRole('button',{name:'Inventory',exact:true}).first().click();await p.getByRole('button',{name:'Purchasing & Counts',exact:true}).click();await p.getByRole('button',{name:'documents',exact:true}).click()};
 await loginBO(backoffice);await documents(backoffice);
 await backoffice.getByLabel('Business document title',{exact:true}).fill('Synthetic full-shell receipt');await backoffice.getByLabel(/^Paper/).selectOption('A4');await backoffice.getByLabel('Use source items, recorded tax and totals blocks').check();
 let response=backoffice.waitForResponse(r=>r.url().endsWith('/api/inventory/workflows/templates')&&r.request().method()==='POST');await backoffice.getByRole('button',{name:'Publish immutable template version',exact:true}).click();const template=await (await response).json();
 await backoffice.getByLabel('Template',{exact:true}).selectOption(template.id);await backoffice.getByLabel('Source record ID',{exact:true}).fill(mixed.sale.id);
 const lostDocument={mode:'drop',matches:(u,req)=>u.pathname==='/api/inventory/workflows/documents'&&req.method()==='POST'};fault=lostDocument;
 await backoffice.getByRole('button',{name:'Render snapshot — no stock or payment',exact:true}).click();await waitFor(()=>lostDocument.seen);assert.equal(lostDocument.status,200);const document=JSON.parse(lostDocument.body.toString());
 response=backoffice.waitForResponse(r=>r.url().endsWith('/api/inventory/workflows/documents')&&r.request().method()==='POST');await backoffice.getByRole('button',{name:'Retry original action',exact:true}).click();const recoveredDoc=await response;assert.equal((await recoveredDoc.json()).id,document.id);assert.equal(recoveredDoc.request().postDataJSON().request_id,JSON.parse(lostDocument.request).request_id);
 await backoffice.getByRole('button',{name:'sale · '+document.id.slice(0,8),exact:true}).click();await backoffice.frameLocator('iframe[title="Saved document preview"]').getByText('Original unpaid credit',{exact:true}).waitFor();
 const lostOutput={mode:'drop',matches:(u,req)=>u.pathname==='/api/inventory/workflows/outputs'&&req.method()==='POST'};fault=lostOutput;
 await backoffice.getByRole('button',{name:'Prepare PDF '+document.id.slice(0,8),exact:true}).click();await waitFor(()=>lostOutput.seen);assert.equal(lostOutput.status,200);const output=JSON.parse(lostOutput.body.toString());
 response=backoffice.waitForResponse(r=>r.url().endsWith('/api/inventory/workflows/outputs')&&r.request().method()==='POST');await backoffice.getByRole('button',{name:'Retry original action',exact:true}).click();assert.equal((await (await response).json()).id,output.id);
 const copies=await Promise.all([1,2,3].map(()=>request('/inventory/workflows/outputs',{company_id:C,request_id:crypto.randomUUID(),document_id:document.id,format:'pdf'},T)));assert.ok(copies.every(r=>r.id===output.id));
 const downloadPath=`/inventory/workflows/outputs/${C}/${output.id}/download`;
 const bytes=async()=>Buffer.from(await (await fetch(API+downloadPath,{headers:{Authorization:'Bearer '+T}})).arrayBuffer());const originalBytes=await bytes();assert.ok(originalBytes.subarray(0,4).toString()==='%PDF');
 let downloads=0;backoffice.on('download',()=>downloads++);const heldDownload={mode:'hold',matches:u=>u.pathname==='/api'+downloadPath};fault=heldDownload;
 await backoffice.getByRole('button',{name:'Download saved output',exact:true}).click();await waitFor(()=>heldDownload.release);await backoffice.getByRole('button',{name:'Log out',exact:true}).first().click();await backoffice.getByRole('button',{name:'Login',exact:true}).waitFor();heldDownload.release();await backoffice.waitForTimeout(150);assert.equal(downloads,0);assert.ok((await bytes()).equals(originalBytes));
 console.log('Backoffice shell lost document/PDF responses recover exact identities and bytes; logout cancels delayed download');
 await loginBO(backoffice);
 const station=await request('/printing/stations',{shop_id:tenant.shop.id,branch_id:B,device_id:auth.device,name:'Synthetic no-delivery station',purpose:'receipt',transport:'system',address:'',paper_width:'80mm',auto_print:false,active:true},T);
 const printerQueue=async p=>{await p.getByRole('button',{name:'Settings',exact:true}).first().click();await p.getByRole('button',{name:/Printers & kitchen/}).click();if(await p.getByRole('button',{name:/^Print queue/}).count())await p.getByRole('button',{name:/^Print queue/}).click();await p.getByLabel(/^Printer station/).selectOption(station.id);await p.getByLabel('Existing sale ID',{exact:true}).fill(mixed.sale.id)};
 await printerQueue(backoffice);const lostPrint={mode:'drop',matches:(u,req)=>u.pathname===`/api/printing/station/${station.id}/jobs`&&req.method()==='POST'};fault=lostPrint;await backoffice.getByRole('button',{name:'Queue original',exact:true}).click();await waitFor(()=>lostPrint.seen);assert.equal(lostPrint.status,200);const job=JSON.parse(lostPrint.body.toString());
 // Persist the retained request across a real shell reload and refresh-cookie rotation.
 await backoffice.reload();await backoffice.getByRole('button',{name:'Log out',exact:true}).first().waitFor();await printerQueue(backoffice);
 response=backoffice.waitForResponse(r=>r.url().endsWith(`/printing/station/${station.id}/jobs`)&&r.request().method()==='POST');await backoffice.getByRole('button',{name:'Queue original',exact:true}).click();const printRecovery=await response;const printJob=await printRecovery.json();assert.equal(printJob.id,job.id);assert.equal(printJob.payload_hash,job.payload_hash);assert.deepEqual(printJob.payload,job.payload);assert.equal(printRecovery.request().postDataJSON().request_key,JSON.parse(lostPrint.request).request_key);
 const jobs=await Promise.all([1,2,3].map(()=>request(`/printing/station/${station.id}/jobs`,JSON.parse(lostPrint.request),T)));assert.ok(jobs.every(r=>r.id===job.id&&r.payload_hash===job.payload_hash));
 console.log('Backoffice shell print enqueue lost response survives reload with exact key/payload; concurrent original requests coalesce');
 await documents(backoffice);const heldOutput={mode:'hold',matches:(u,req)=>u.pathname==='/api/inventory/workflows/outputs'&&req.method()==='POST'};fault=heldOutput;await backoffice.getByRole('button',{name:'Prepare PDF '+document.id.slice(0,8),exact:true}).click();await waitFor(()=>heldOutput.release);
 const second=await context.newPage();await second.goto(BO);await second.getByRole('button',{name:'Log out',exact:true}).first().waitFor();await second.getByRole('button',{name:'Log out',exact:true}).first().click();await second.getByRole('button',{name:'Login',exact:true}).waitFor();await loginBO(second);await backoffice.getByRole('button',{name:'Login',exact:true}).waitFor();heldOutput.release();await backoffice.waitForTimeout(100);assert.equal(await backoffice.getByRole('button',{name:'Download saved output',exact:true}).count(),0);assert.ok((await bytes()).equals(originalBytes));
 console.log('Concurrent authenticated Backoffice tab replaces old context; late output cannot install in signed-out shell');
 
 await page.getByRole('button',{name:'Settings',exact:true}).click();await page.locator('.pos-settings-menu-item').filter({hasText:'Printer'}).click();await page.getByRole('button',{name:/^Print queue/}).click();await page.getByLabel(/^Printer station/).selectOption(station.id);
 const claimHold={mode:'hold',matches:u=>u.pathname===`/api/printing/jobs/${job.id}/claim`};fault=claimHold;let popups=0;page.on('popup',()=>popups++);
 await page.getByRole('button',{name:'Print',exact:true}).click();await waitFor(()=>claimHold.release);assert.equal(claimHold.status,200);
 await page.getByRole('button',{name:'Log out',exact:true}).click();await page.locator('input[type=email]').waitFor();claimHold.release();await page.waitForTimeout(150);assert.equal(popups,0);
 const deniedReady=await fetch(API+`/printing/jobs/${job.id}/ready`,{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+auth.token},body:claimHold.request});assert.equal(deniedReady.status,401);
 console.log('POS actual print claim held across logout: no transport; revoked session cannot obtain readiness');
 // Reauthenticate via the original shell before checking delayed historical reprint.
 await page.locator('input[type=email]').fill(tenant.user.email);await page.locator('input[type=password]').fill(password);await page.getByRole('button',{name:'Sign in',exact:true}).last().click();await page.getByRole('button',{name:'Open POS',exact:true}).waitFor();await page.locator('input').filter({visible:true}).first().fill('1234');await page.getByRole('button',{name:'Open POS',exact:true}).click();await page.getByRole('button',{name:'Transaction History',exact:true}).click();
 
// POS reprint callback receives a real authorized response only after local logout.
 const heldReprint={mode:'hold',matches:u=>u.pathname===`/api/sales/receipt/${C}/${mixed.sale.id}`};fault=heldReprint;
 await page.getByRole('row').filter({hasText:mixed.sale.receipt_number}).getByRole('button',{name:'Reprint',exact:true}).click();await waitFor(()=>heldReprint.release);await page.getByRole('button',{name:'Log out',exact:true}).click();await page.locator('input[type=email]').waitFor();heldReprint.release();await page.waitForTimeout(100);assert.equal(await page.getByRole('dialog').count(),0);
 writeFileSync('/tmp/phase11-shell-result.json',JSON.stringify({company:C,product:product.id,original:mixed.sale.id,refund:returned.sale.id,document:document.id,output:output.id,job:job.id,actual_shell_navigation_authentication:true,persisted_split_original_refund:true,exact_lost_document_output_and_print_recovery:true,concurrent_original_requests_coalesce:true,logout_drops_receipt_reprint_and_download:true,concurrent_tab_replacement_drops_output:true,claim_logout_no_transport_and_readiness_revoked:true,saved_output_bytes_unchanged:true,real_transport_invoked:false,physical_printer_acceptance:false,split_posting_release_enabled:false,errors,unexpected},null,2)+'\n');

 
 console.log(JSON.stringify({errors,unexpected}));
}finally{await browser.close()}
