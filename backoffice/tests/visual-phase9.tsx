// Synthetic browser-only adapter. No backend or ZIMRA requests.
import { createRoot } from 'react-dom/client';
import { AxiosError } from 'axios';
import { api } from '../src/api/client';
import FiscalSettingsPanel from '../src/pages/FiscalSettingsPanel';
import '../src/index.css';
import '../src/theme.css';
import '../src/pages/settings.css';
const calls: unknown[] = [];
Object.assign(window, { phase9Calls: calls });
const denied = new URLSearchParams(location.search).has('denied');
let settings: unknown = null, version = 0;
api.defaults.adapter = async config => {
  const url = config.url || '', method = config.method;
  const body = typeof config.data === 'string' ? JSON.parse(config.data) : config.data;
  calls.push({ url, method, body });
  if (denied) throw new AxiosError('Forbidden', 'ERR_BAD_REQUEST', config, undefined, { config, status: 403, statusText: 'Forbidden', headers: {}, data: { detail: 'Owner required' } });
  let data: unknown = [];
  if (url.includes('/configuration')) {
    if (method === 'put') { settings = body; version++; }
    data = { version, settings, blockers: ['ZIMRA test onboarding', 'Device certificate and signing verification', 'Formal approval'] };
  } else if (url.includes('/devices/branches/')) data = [{ id: 'branch-test', name: 'Synthetic branch' }];
  else if (url.includes('/devices/')) data = [{ id: 'register-test', name: 'Synthetic register', branch_id: 'branch-test' }];
  return { data, config, status: 200, statusText: 'OK', headers: {} };
};
createRoot(document.getElementById('root')!).render(<main style={{ padding: 16 }}><FiscalSettingsPanel companyId="synthetic-business" /></main>);
