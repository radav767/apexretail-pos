import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';
import { chromium } from '/root/.npm/_npx/420ff84f11983ee5/node_modules/playwright/index.mjs';

const root=fileURLToPath(new URL('..',import.meta.url));
const server=await createServer({root,resolve:{dedupe:['react','react-dom']},server:{host:'127.0.0.1',port:18931,strictPort:true}});
await server.listen();
const browser=await chromium.launch({executablePath:'/tmp/apexretail-pw-browsers/chromium-1194/chrome-linux/chrome',args:['--no-sandbox']});
const context=await browser.newContext();const checks=[],external=[],errors=[];
await context.route('**/*',route=>new URL(route.request().url()).hostname==='127.0.0.1'?route.continue():(external.push(route.request().url()),route.abort()));
const page=await context.newPage();page.on('dialog',dialog=>dialog.accept());page.on('pageerror',error=>errors.push(error.message));
const out=fileURLToPath(new URL('../../artifacts/phase7-final-development',import.meta.url));await mkdir(out,{recursive:true});
function pass(name){checks.push(name);}
async function open(app,feature,extra=''){
 await page.goto(`http://127.0.0.1:18931/tests/visual-final-catalog.html?app=${app}&feature=${feature}${extra}`);
 await page.getByRole('heading',{name:feature==='variants'||feature==='product-variants'?'Product Variants':feature==='price-levels'?'Price Levels':'Categories',exact:true}).waitFor();
 if(feature!=='categories')await page.locator(app==='backoffice'?'.advanced-product-picker select':'.pos-product-picker select').selectOption('product');
}
try{
 await page.goto('http://127.0.0.1:18931/tests/visual-final-catalog.html?app=module&feature=all-products&costs=false');
 await page.getByRole('heading',{name:'Product Management',exact:true}).waitFor();
 assert.equal(await page.getByLabel('Cost price',{exact:true}).count(),0);
 await page.getByRole('row').filter({hasText:'Synthetic stock item'}).getByRole('button',{name:'Edit',exact:true}).click();
 await page.getByLabel('Product name',{exact:true}).fill('Edited stock item');
 await page.getByRole('button',{name:'Update Product',exact:true}).click();
 await page.getByRole('row').filter({hasText:'Edited stock item'}).waitFor();
 const productEdit=await page.evaluate(()=>window.catalogRequests.find(r=>r.method==='patch'));
 assert.equal('cost_price' in productEdit.payload,false);pass('POS product edit omits restricted cost');
 await page.getByRole('row').filter({hasText:'Edited stock item'}).getByRole('button',{name:'Archive',exact:true}).click();
 await page.getByText('Product archived.',{exact:true}).waitFor();pass('POS product archive uses existing API');
 await page.goto('http://127.0.0.1:18931/tests/visual-final-catalog.html?app=module&feature=all-products&restricted=true&costs=false');
 await page.getByRole('heading',{name:'Available Products',exact:true}).waitFor();
 for(const name of ['Edit','Archive','Create Product'])assert.equal(await page.getByRole('button',{name,exact:true}).count(),0);
 pass('POS product explicit add/edit/delete denials hide mutation actions');
 for(const app of ['pos','backoffice']){
  await page.goto(`http://127.0.0.1:18931/tests/visual-final-catalog.html?app=${app}&feature=stock-count`);
  await page.getByLabel('Physical count Synthetic stock item — Small',{exact:true}).fill('6');
  await page.getByRole('button',{name:'Complete Stock Take (1)',exact:true}).click();
  await page.getByRole('button',{name:'Retry original count',exact:true}).waitFor();
  const command=await page.evaluate(()=>window.catalogRequests.find(r=>r.url==='/inventory/stock-take').payload);
  assert.equal(command.items[0].variant_id,'variant');assert.equal(command.items[0].expected_qty,'8');
  await page.reload();await page.getByRole('button',{name:'Retry original count',exact:true}).click();
  await page.waitForFunction(()=>window.catalogRequests.some(r=>r.url==='/inventory/stock-take'));
  assert.deepEqual(await page.evaluate(()=>window.catalogRequests.find(r=>r.url==='/inventory/stock-take').payload),command);
  await page.getByRole('button',{name:'Retry original count',exact:true}).click();
  await page.getByRole('button',{name:'New stock count',exact:true}).waitFor();pass(`${app}: variant count keeps snapshot and original identity through timeout/restart`);
 }
 for(const app of ['pos','backoffice']){
  await page.goto(`http://127.0.0.1:18931/tests/visual-final-catalog.html?app=${app}&feature=transfers`);
  const selects=page.locator(app==='pos'?'.business-form select':'.inventory-form-grid select');
  await selects.nth(1).selectOption('destination');await selects.nth(2).selectOption('product');
  await page.locator(app==='pos'?'.business-form input[type=number]':'.inventory-form-grid input[type=number]').fill('3');await page.getByRole('button',{name:'Transfer Stock',exact:true}).click();
  await page.getByRole('button',{name:'Retry original transfer',exact:true}).waitFor();
  const original=await page.evaluate(()=>window.catalogRequests.find(r=>r.url==='/inventory/transfers').payload);
  assert.ok(original.request_id);await page.reload();
  await page.getByRole('button',{name:'Retry original transfer',exact:true}).click();
  await page.waitForFunction(()=>window.catalogRequests.some(r=>r.url==='/inventory/transfers'));
  const retry=await page.evaluate(()=>window.catalogRequests.find(r=>r.url==='/inventory/transfers').payload);
  assert.deepEqual(retry,original);pass(`${app}: transfer timeout/reload retains original protected payload`);
  await page.getByRole('button',{name:'Retry original transfer',exact:true}).click();
  await page.getByRole('button',{name:'New transfer',exact:true}).waitFor();pass(`${app}: original transfer retry confirms without replacement identity`);
  // A frontend talking to an older backend must never advertise safe retry
  // merely because its local payload contains a request_id.
  await page.getByRole('button',{name:'New transfer',exact:true}).click();
  await page.goto(`http://127.0.0.1:18931/tests/visual-final-catalog.html?app=${app}&feature=transfers&legacy=true`);
  const legacySelects=page.locator(app==='pos'?'.business-form select':'.inventory-form-grid select');
  await legacySelects.nth(1).selectOption('destination');await legacySelects.nth(2).selectOption('product');
  await page.locator(app==='pos'?'.business-form input[type=number]':'.inventory-form-grid input[type=number]').fill('3');await page.getByRole('button',{name:'Transfer Stock',exact:true}).click();
  await page.waitForFunction(()=>window.catalogRequests.some(r=>r.url==='/inventory/transfers'));
  assert.equal(await page.getByRole('button',{name:'Retry original transfer',exact:true}).count(),0);pass(`${app}: legacy backend cannot enable protected retries`);
 }
 for(const app of ['pos','backoffice']){
  await open(app,app==='pos'?'product-variants':'variants');
  let row=page.getByRole('row').filter({hasText:'Small'});await row.getByRole('button',{name:'Edit',exact:true}).click();
  await page.getByPlaceholder('Variant name',{exact:true}).fill('Small green');
  await page.getByPlaceholder('Selling price',{exact:true}).fill('6');
  assert.equal(await page.getByPlaceholder('Opening stock',{exact:true}).count(),0);
  await page.getByRole('button',{name:'Update variant',exact:true}).click();
  row=page.getByRole('row').filter({hasText:'Small green'});await row.waitFor();
  const edit=await page.evaluate(()=>window.catalogRequests.find(r=>r.method==='patch'));
  assert.equal(edit.payload.stock_qty,undefined);assert.equal(edit.payload.attributes,undefined);assert.equal(edit.payload.selling_price,'6');pass(`${app}: variant edit preserves stock and attributes`);
  await row.getByRole('button',{name:'Archive',exact:true}).click();await row.getByRole('button',{name:'Restore',exact:true}).waitFor();
  await row.getByRole('button',{name:'Restore',exact:true}).click();await row.getByRole('button',{name:'Archive',exact:true}).waitFor();pass(`${app}: variant archive and restore`);
  await page.getByPlaceholder('Variant name',{exact:true}).fill('Large');await page.getByRole('button',{name:'Add variant',exact:true}).click();
  await page.getByRole('row').filter({hasText:'Large'}).waitFor();pass(`${app}: variant create`);
  await open(app,'price-levels');row=page.getByRole('row').filter({hasText:'Wholesale'});await row.getByRole('button',{name:'Edit',exact:true}).click();
  await page.getByPlaceholder('Price',{exact:true}).fill('3.50');await page.getByRole('button',{name:'Update price level',exact:true}).click();
  await page.waitForFunction(()=>window.catalogRequests.some(r=>r.method==='patch'&&r.payload.price==='3.50'));pass(`${app}: price level edit`);
  await row.getByRole('button',{name:'Delete',exact:true}).click();await row.waitFor({state:'detached'});pass(`${app}: price level delete`);
  await page.getByPlaceholder(app==='pos'?'Price level':'Level name',{exact:true}).fill('VIP');await page.getByPlaceholder('Price',{exact:true}).fill('4');
  await page.getByRole('button',{name:app==='pos'?'Add price level':'Add price',exact:true}).click();await page.getByRole('row').filter({hasText:'VIP'}).waitFor();pass(`${app}: price level create`);
 }
 await open('pos','categories');await page.getByPlaceholder('Category name',{exact:true}).fill('New category');await page.getByRole('button',{name:'Add',exact:true}).click();
 let row=page.getByRole('row').filter({hasText:'New category'});await row.getByRole('button',{name:'Edit',exact:true}).click();await page.getByPlaceholder('Category name',{exact:true}).fill('Renamed category');await page.getByRole('button',{name:'Update',exact:true}).click();
 row=page.getByRole('row').filter({hasText:'Renamed category'});await row.getByRole('button',{name:'Delete',exact:true}).click();await row.waitFor({state:'detached'});pass('POS: category create/edit/delete');
 await page.getByRole('row').filter({hasText:'Existing category'}).getByRole('button',{name:'Delete',exact:true}).click();await page.getByText('Category contains products',{exact:true}).waitFor();pass('POS: dependent category deletion displays backend rejection');
 await page.getByPlaceholder('Search categories').fill('missing');assert.equal(await page.locator('tbody tr').count(),0);pass('POS: category search');
 await open('backoffice','categories');await page.getByPlaceholder('Category name',{exact:true}).fill('New BO category');await page.getByRole('button',{name:'Add',exact:true}).click();
 let category=page.locator('.category-row').filter({hasText:'New BO category'});await category.getByRole('button',{name:'Edit',exact:true}).click();
 await page.getByPlaceholder('Category name',{exact:true}).fill('Renamed BO category');await page.getByRole('button',{name:'Update',exact:true}).click();
 category=page.locator('.category-row').filter({hasText:'Renamed BO category'});await category.getByRole('button',{name:'Delete',exact:true}).click();await category.waitFor({state:'detached'});pass('Backoffice: category create/edit/delete');
 await page.locator('.category-row').filter({hasText:'Existing category'}).getByRole('button',{name:'Delete',exact:true}).click();await page.getByText('Category contains products',{exact:true}).waitFor();pass('Backoffice: dependent category deletion displays backend rejection');
 await page.getByPlaceholder('Search categories').fill('missing');assert.equal(await page.locator('.category-row').count(),0);pass('Backoffice: category search');
 await page.goto('http://127.0.0.1:18931/tests/visual-final-catalog.html?feature=batch-count');
 await page.getByText('Receive / return / dispose / count batch stock',{exact:true}).click();
 await page.locator('.business-form select').nth(1).selectOption('product');await page.getByLabel('Batch code',{exact:true}).fill('COUNT');
 await page.getByLabel('Expiry date',{exact:true}).fill('2027-01-01');await page.getByLabel('Actual batch quantity counted',{exact:true}).fill('0');await page.getByLabel('Reason',{exact:true}).fill('Physical count');
 await page.getByRole('button',{name:'Confirm stock operation',exact:true}).click();await page.getByRole('button',{name:'Retry original stock request',exact:true}).waitFor();
 await page.reload();await page.getByText('Receive / return / dispose / count batch stock',{exact:true}).click();
 await page.getByRole('button',{name:'Retry original stock request',exact:true}).click();
 // Reload deliberately resets the synthetic server: the persisted command still
 // retains its identity, zero quantity and operation after another timeout.
 const saved=await page.evaluate(()=>JSON.parse(localStorage.getItem('apexretail_batch_command_v1:synthetic-count')));
 const attempts=await page.evaluate(()=>window.catalogRequests.filter(r=>r.url==='/operations/batches/stock'));
 assert.equal(saved.payload.operation,'count');assert.equal(saved.payload.quantity,'0');assert.equal(attempts[0].payload.request_id,saved.payload.request_id);pass('Batch count: zero count and original request survive timeout/reload');
 await page.getByRole('button',{name:'Retry original stock request',exact:true}).click();await page.getByRole('button',{name:'New stock operation',exact:true}).waitFor();pass('Batch count: confirmed retry unlocks a new operation');
 await open('pos','product-variants','&restricted=true&costs=false');assert.equal(await page.getByRole('button',{name:'Edit',exact:true}).count(),0);assert.equal(await page.getByRole('columnheader',{name:'Cost',exact:true}).count(),0);pass('POS: restricted controls and costs hidden');
 const access=await page.evaluate(()=>{
  const actor={role:'cashier',permissions:{manage_products:true,variants_manage:false,categories_manage:true}};
  return [window.catalogAccess.canManageProductTool(actor,'product-variants'),window.catalogAccess.canManageProductTool(actor,'categories'),window.catalogAccess.catalogPermission({role:'cashier',permissions:{}},'product_costs_view')];
 });assert.deepEqual(access,[false,true,false]);pass('Explicit granular denial overrides broad legacy permission');
 for(const width of [320,390,820,1440]){
  await page.setViewportSize({width,height:900});
  await open('pos','product-variants');await page.getByRole('row').filter({hasText:'Small'}).waitFor();
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));pass(`POS catalog ${width}px no horizontal overflow`);
  await page.screenshot({path:`${out}/pos-variants-${width}.png`,fullPage:true});
  await open('backoffice','variants');await page.getByRole('row').filter({hasText:'Small'}).waitFor();
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));pass(`Backoffice catalog ${width}px no horizontal overflow`);
  await page.screenshot({path:`${out}/backoffice-variants-${width}.png`,fullPage:true});
 }
 assert.deepEqual(external,[]);assert.deepEqual(errors,[]);pass('No production/external requests or uncaught page errors');
 console.log(JSON.stringify({passed:checks.length,checks},null,2));
}catch(error){process.exitCode=1;console.error(error);await page.screenshot({path:`${out}/failure.png`,fullPage:true});}
finally{await writeFile(`${out}/catalog-browser-results.json`,JSON.stringify({checks,external,errors,physicalHardware:false,passed:!process.exitCode},null,2));await browser.close();await server.close();}
