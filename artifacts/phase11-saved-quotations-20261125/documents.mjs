import {readFileSync,writeFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import assert from 'node:assert/strict';
import ts from '/tmp/apex-phase11-build-xijhpj7t/pos-web/node_modules/typescript/lib/typescript.js';
const root='/tmp/apexpos-phase11';
async function compile(source){const js=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;return import('data:text/javascript;base64,'+Buffer.from(js).toString('base64'))}
const actual=await compile(readFileSync(root+'/pos-web/src/business/documents.ts','utf8'));
const old=await compile(execFileSync('git',['show','7d8d619:pos-web/src/business/documents.ts'],{cwd:root,encoding:'utf8'}));
const result=JSON.parse(readFileSync('/tmp/phase11-quotation-shell-result.json','utf8')),order=result.saved_order;
const html=actual.quotationHtml(order);
for(const value of ['69.00 USD','10353 JPY','0.5 box / 6.0000 each','69.00 / 3.00 / 0.00','NOT A PAYMENT RECEIPT'])assert.ok(html.includes(value),value);
const malicious=structuredClone(order);malicious.items[0].name='<script>synthetic()</script>';malicious.number='<img src=x onerror=synthetic()>';
const safe=actual.quotationHtml(malicious);assert.ok(!safe.includes('<script>'));assert.ok(safe.includes('&lt;script&gt;'));assert.ok(!safe.includes('<img src=x'));
const legacy={...order,quotation_terms:{total:'24.00',tax:'0.00',currency:'USD'},quotation_pricing:null};assert.equal(actual.quotationHtml(legacy),old.quotationHtml(legacy));
writeFileSync('/tmp/phase11-quotation-preview.html',html);
writeFileSync('/tmp/phase11-quotation-documents.json',JSON.stringify({synthetic_only:true,actual_persisted_v2_plan_exact_units_discounts_tax_currency:true,escaped_untrusted_text:true,v1_output_byte_identical_to_7d8d619:true,software_html_only_no_printer_or_provider:true},null,2)+'\n');
console.log('Quotation HTML: persisted v2 values match; untrusted text escaped; v1 bytes unchanged. No printer/provider invoked.');
