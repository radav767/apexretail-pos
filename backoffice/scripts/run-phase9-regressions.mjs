// Existing local dependencies only; no network, deployment, Android build or DB access.
import { spawnSync } from 'node:child_process';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
const root = fileURLToPath(new URL('../..', import.meta.url));
const out = `${root}/artifacts/phase9-fiscal/frontend`;
await mkdir(out, { recursive: true });
const results = [];
for (const app of ['pos-web', 'backoffice']) {
  const manifest = JSON.parse(await readFile(`${root}/${app}/package.json`, 'utf8'));
  const commands = [...Object.keys(manifest.scripts).filter(key => key.startsWith('test:')), 'lint', 'build'];
  for (const script of commands) {
    const args = ['run', script, ...(app === 'backoffice' && script === 'build' ? ['--', '--base=/backoffice/'] : [])];
    const result = spawnSync('npm', args, { cwd: `${root}/${app}`, encoding: 'utf8', maxBuffer: 16 * 1024 * 1024,
      env: { ...process.env, VITE_API_BASE_URL: 'https://localhost:18770/api',
        ENTITLEMENT_PUBLIC_KEYRING_FILE: `${root}/phase7g-evidence/staging-public-keyring.json` } });
    await writeFile(`${out}/${app}-${script.replaceAll(':', '-')}.log`, `${result.stdout || ''}${result.stderr || ''}`);
    results.push({ app, script, exit_code: result.status, error: result.error?.message });
    console.log(`${app} ${script}: ${result.status === 0 && !result.error ? 'PASS' : 'FAIL'}`);
  }
}
await writeFile(`${out}/results.json`, JSON.stringify(results, null, 2));
if (results.some(result => result.exit_code !== 0 || result.error)) process.exitCode = 1;
