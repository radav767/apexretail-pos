import { readFileSync, writeFileSync } from 'node:fs';
import assert from 'node:assert/strict';
import { chromium } from '/tmp/apex-phase11-browser-tools/node_modules/playwright/index.mjs';
const fixtures=JSON.parse(readFileSync('/tmp/phase11-split-receipt-fixtures.json','utf8'));
const browser=await chromium.launch({executablePath:'/root/.cache/ms-playwright/chromium_headless_shell-1243/chrome-headless-shell-linux64/chrome-headless-shell',headless:true,args:['--no-sandbox','--disable-background-networking']});
const results=[],unexpected=[],errors=[];
try {
 const context=await browser.newContext({viewport:{width:420,height:900}});
 await context.route('**/*',route=>{unexpected.push(route.request().url());return route.abort()});
 const page=await context.newPage();page.on('pageerror',error=>errors.push(String(error)));
 for(const kind of ['original','refund'])for(const width of ['58mm','80mm']) {
  await page.setContent(readFileSync(`/tmp/${kind}-${width}.html`,'utf8'));
  const rows=await page.locator('dl.split-payment > div').evaluateAll(nodes=>nodes.map(n=>[n.querySelector('dt').textContent,n.querySelector('dd').textContent]));
  assert.deepEqual(rows,fixtures[kind].split_accounting.rows);
  assert.equal(await page.locator('dl[aria-label="Recorded split allocations"]').count(),1);
  assert.equal(await page.getByText('Paid',{exact:true}).count(),0);
  assert.ok(await page.locator('.split-payment').evaluate(n=>n.scrollWidth<=n.clientWidth+1),'58/80mm allocations fit without clipping');
  await page.emulateMedia({media:'print'});
  await page.pdf({path:`/tmp/phase11-split-preview-${kind}-${width}.pdf`,format:'A4',printBackground:true});
  results.push({kind,width,ordered_disclosure_matches_persisted_payload:true,no_scalar_paid:true,no_horizontal_clipping:true,software_print_pdf:true});
 }
 assert.deepEqual(unexpected,[]);assert.deepEqual(errors,[]);
 writeFileSync('/tmp/phase11-split-receipt-browser.json',JSON.stringify({results,unexpected_requests:unexpected,page_errors:errors,hardware_acceptance:false,posting_enabled:false},null,2)+'\n');
 console.log(JSON.stringify({receipt_previews:results.length,unexpected_requests:unexpected,page_errors:errors,posting_enabled:false,hardware_acceptance:false}));
} finally {await browser.close()}
