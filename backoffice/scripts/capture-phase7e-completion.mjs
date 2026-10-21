import assert from "node:assert/strict";
import {mkdir,writeFile} from "node:fs/promises";
import {resolve} from "node:path";
import {pathToFileURL} from "node:url";
import {spawn} from "node:child_process";
const root=resolve(import.meta.dirname,"../..");const output=process.env.UI_AUDIT_OUTPUT_DIR||resolve(root,"phase7e-evidence/completion/preview");await mkdir(output,{recursive:true});
const {chromium}=await import(pathToFileURL(process.env.PLAYWRIGHT_MODULE).href);
const base="http://127.0.0.1:5194/tests/visual-phase7e-completion.html";
const server=spawn(process.execPath,[resolve(root,"backoffice/node_modules/vite/bin/vite.js"),"--host","127.0.0.1","--port","5194","--strictPort"],{cwd:resolve(root,"backoffice"),stdio:"ignore"});
let browser;const checks=[];const images=[];
try{
 for(let n=0;n<80;n++){try{if((await fetch(base)).ok)break;}catch{}await new Promise(r=>setTimeout(r,200));}
 browser=await chromium.launch({executablePath:process.env.CHROMIUM_EXECUTABLE,headless:true,args:["--no-sandbox"]});
 for(const [device,width,height] of [["desktop",1440,1000],["tablet",820,1180],["android",390,844],["narrow",320,740]]){
  for(const feature of ["stock-transfers","sales-reports","top-products","batches"]){
   const context=await browser.newContext({viewport:{width,height}});const page=await context.newPage();const errors=[];page.on("pageerror",e=>errors.push(e.message));page.on("dialog",d=>d.accept());await context.route("https://**/*",r=>r.abort());
   await page.goto(`${base}?feature=${feature}${feature==="stock-transfers"?"&timeout=1":""}`);
   if(feature==="stock-transfers"){
    await page.getByLabel(/^Destination branch/).selectOption("destination");await page.getByLabel(/^Product/).selectOption("product");await page.getByLabel("Quantity",{exact:true}).fill("3");
   }else if(feature==="batches"){
    await page.getByText("Batch inventory valuation",{exact:true}).click();await page.getByRole("button",{name:"View batch valuation",exact:true}).click();await page.getByText("Synthetic medicine — 500mg",{exact:true}).waitFor();
    const download=page.waitForEvent("download");await page.getByRole("button",{name:"Export batch valuation CSV",exact:true}).click();await download;
   }else{await page.getByRole("button",{name:"View report",exact:true}).click();await page.getByText(feature==="top-products"?"Synthetic stock":"SYN-0042",{exact:true}).waitFor();const download=page.waitForEvent("download");await page.getByRole("button",{name:"Export CSV",exact:true}).click();await download;}
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);const file=`${feature}-${device}.png`;await page.screenshot({path:resolve(output,file),fullPage:true});images.push(file);
   if(feature==="stock-transfers"){
    await page.getByRole("button",{name:"Transfer Stock",exact:true}).click();await page.getByRole("button",{name:"Check original transfer",exact:true}).waitFor();
    await page.reload();await page.getByRole("button",{name:"Check original transfer",exact:true}).click();await page.getByText("Original stock transfer confirmed from history.",{exact:true}).waitFor();
    assert.equal(await page.evaluate(()=>window.__completionCalls.filter(c=>c.method==="post").length),0);
   }
   assert.deepEqual(errors,[]);checks.push({device,feature,overflow:false,action:feature==="stock-transfers"?"timeout retained across reload; original transfer confirmed without repost":"real component report and CSV using synthetic adapter",physicalHardware:false});
   await context.close();
  }
  const page=await browser.newPage();for(const feature of ["stock-transfers","sales-reports","top-products"]){await page.goto(`${base}?feature=${feature}&denied=1`);await page.getByText("Permission denied.",{exact:true}).waitFor();assert.equal(await page.evaluate(()=>window.__completionCalls.length),0);}await page.close();
 }
 await writeFile(resolve(output,"checks.json"),JSON.stringify({checks,screenshots:images.length,permissionDeniedNoApi:true,syntheticOnly:true},null,2));
 await writeFile(resolve(output,"index.html"),`<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><title>Phase 7E completion</title><style>body{font:16px system-ui;background:#f5f7f8;color:#20252b;margin:16px}h1{color:#07583b}article{max-width:1100px;margin:24px auto}img{width:100%;border:1px solid #ddd;border-radius:12px}</style><h1>ApexRetail · Completion review</h1><p>Actual React components · Synthetic data · Not deployed</p>${images.map(i=>`<article><h2>${i}</h2><a href="${i}"><img loading="lazy" src="${i}"></a></article>`).join("")}`);
 console.log(JSON.stringify({checks:checks.length,screenshots:images.length,permissionDeniedNoApi:true}));
}finally{await browser?.close();server.kill("SIGTERM");}
