/** Complete source-control inventory, NOT a claim that every action was tested.
 * JSX controls and form submissions are catalogued separately from test results.
 * Dynamic grids retain their expression/handler and require item-by-item review.
 */
import ts from "typescript";
import { readdir, readFile, writeFile, mkdir } from "node:fs/promises";
import { resolve, relative } from "node:path";
const root = resolve(import.meta.dirname, "../..");
const output = resolve(root, "phase7e-evidence/stabilization/audit"); await mkdir(output,{recursive:true});
async function files(dir, extension) {
  const all=[];
  for (const entry of await readdir(dir,{withFileTypes:true})) {
    if (entry.isDirectory()) all.push(...await files(resolve(dir,entry.name),extension));
    else if(entry.name.endsWith(extension)) all.push(resolve(dir,entry.name));
  }
  return all;
}
const rows=[];
const normalize=value=>String(value).replace(/\s+/g," ").trim();
for (const project of ["pos-web","backoffice"]) {
  for (const file of await files(resolve(root,project,"src"),".tsx")) {
    const source=await readFile(file,"utf8"); const ast=ts.createSourceFile(file,source,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
    function visit(node) {
      const opening=ts.isJsxElement(node)?node.openingElement:ts.isJsxSelfClosingElement(node)?node:null;
      if(opening) {
        const tag=opening.tagName.getText(ast);
        const attrs=Object.fromEntries(opening.attributes.properties.filter(ts.isJsxAttribute).map(a=>[a.name.getText(ast),normalize(a.initializer?.getText(ast)||"")]));
        if (["button","form","a","select","input"].includes(tag) || Object.keys(attrs).some(a=>/^on(Click|Submit|Select|Change|Save|Delete|Edit|Navigate|Export|Print)$/.test(a))) {
          const line=ast.getLineAndCharacterOfPosition(node.getStart(ast)).line+1;
          const text=normalize(ts.isJsxElement(node)?node.children.map(n=>n.getText(ast)).join(" "):attrs["aria-label"]||attrs.title||attrs.name||attrs.type||tag);
          rows.push({feature:`${project}/${relative(resolve(root,project,"src"),file)}`, action:text.slice(0,180), control:tag,
            source:`${relative(root,file)}:${line}`, handler:Object.entries(attrs).filter(([k])=>/^on|href/.test(k)).map(([k,v])=>`${k}=${v}`).join(" ").slice(0,1200),
            test_result:"NOT VERIFIED end-to-end", remaining_limitation:"Source inventory only. See test-action matrix for separately verified behaviors; dynamic controls need per-item authenticated acceptance."});
        }
      }
      ts.forEachChild(node,visit);
    }
    visit(ast);
  }
}
const field=value=>`"${String(value??"").replaceAll('"','""')}"`;
const keys=["feature","action","test_result","remaining_limitation","source","control","handler"];
await writeFile(resolve(output,"ui-action-inventory.csv"),[keys,...rows.map(r=>keys.map(k=>r[k]))].map(r=>r.map(field).join(",")).join("\r\n"));
await writeFile(resolve(output,"ui-action-inventory.json"),JSON.stringify({scope:"All source JSX controls, including dynamic templates; not runtime coverage",controls:rows.length,files:new Set(rows.map(r=>r.feature)).size,rows},null,2));
console.log(JSON.stringify({controls:rows.length,files:new Set(rows.map(r=>r.feature)).size,allRuntimeActionsVerified:false}));
