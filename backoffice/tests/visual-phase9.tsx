// Synthetic browser-only adapter. No backend or ZIMRA requests.
import { createRoot } from 'react-dom/client';
import { AxiosError } from 'axios';
import { api } from '../src/api/client';
import FiscalSettingsPanel from '../src/pages/FiscalSettingsPanel';
import FiscalSaleStatus from '../../pos-web/src/components/FiscalSaleStatus';
import { api as posApi } from '../../pos-web/src/api/client';
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
  else if (url.endsWith('/runtime')) data = { day_status: 'not_initialised', day_no: null, pending_operation: null, documents: [] };
  else if (url.includes('/sales/') && url.endsWith('/status')) data = { configured: true,
    status: new URLSearchParams(location.search).has('uncertain') ? 'test_submission_requires_review' : 'acknowledged_test_validation_unknown',
    environment: 'test', certified: false, submitted: null };
  else if (url.includes('/devices/')) data = [{ id: 'register-test', name: 'Synthetic register', branch_id: 'branch-test' }];
  return { data, config, status: 200, statusText: 'OK', headers: {} };
};
posApi.defaults.adapter = api.defaults.adapter;
createRoot(document.getElementById('root')!).render(<main style={{ padding: 16 }}>{new URLSearchParams(location.search).has('pos')
  ? <FiscalSaleStatus companyId="synthetic-business" saleId="synthetic-sale" />
  : <FiscalSettingsPanel companyId="synthetic-business" />}</main>);
