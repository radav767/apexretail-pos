import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { resolve } from 'node:path';
import { spawnSync } from 'node:child_process';
const root=resolve(import.meta.dirname,'..');
const output=mkdtempSync(resolve(tmpdir(),'apex-shift-policy-'));
writeFileSync(resolve(output,'package.json'),JSON.stringify({type:'module'}));
try{
  const compile=spawnSync(resolve(root,'node_modules/.bin/tsc'),['--ignoreConfig','--target','ES2023','--module','NodeNext','--moduleResolution','NodeNext','--types','node','--skipLibCheck','--outDir',output,'src/shiftPolicy.ts','tests/shiftPolicy.test.ts'],{cwd:root,stdio:'inherit'});
  if(compile.status!==0)throw Error('Shift policy test compilation failed');
  process.exitCode=spawnSync(process.execPath,[resolve(output,'tests/shiftPolicy.test.js')],{stdio:'inherit'}).status??1;
}finally{rmSync(output,{recursive:true,force:true});}
