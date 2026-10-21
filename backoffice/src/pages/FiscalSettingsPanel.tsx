import { useEffect, useState } from 'react';
import { api } from '../api/client';

type Option = { id: string; name: string; branch_id?: string };
type Draft = {
  environment: 'test' | 'production'; taxpayer_tin: string; vat_number: string | null;
  branch_id: string; register_id: string; device_id: number; device_serial: string;
  model_name: string; model_version: string;
};
type Status = { version: number; settings: (Draft & { credential_configured: boolean; taxes: unknown[] }) | null; blockers: string[] };
type RecordRow = { id: string; sale_id: string; state: string; sha256: string };
const empty: Draft = { environment: 'test', taxpayer_tin: '', vat_number: null, branch_id: '', register_id: '', device_id: 1, device_serial: '', model_name: '', model_version: '' };
function message(error: unknown): string {
  const response = (error as { response?: { data?: { detail?: unknown }; status?: number } }).response;
  return response?.status === 403 ? 'Business owner account required.' : typeof response?.data?.detail === 'string' ? response.data.detail : 'Fiscal settings unavailable. Reconnect and retry.';
}

export default function FiscalSettingsPanel({ companyId }: { companyId: string }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [draft, setDraft] = useState<Draft>(empty);
  const [branches, setBranches] = useState<Option[]>([]), [devices, setDevices] = useState<Option[]>([]);
  const [records, setRecords] = useState<RecordRow[]>([]);
  const [taxes, setTaxes] = useState('[]'), [saleId, setSaleId] = useState('');
  const [notice, setNotice] = useState(''), [busy, setBusy] = useState(false);
  const [audits, setAudits] = useState<{ action: string; created_at: string }[]>([]);
  useEffect(() => {
    let current = true;
    setStatus(null); setDraft(empty); setTaxes('[]'); setNotice(''); setRecords([]); setAudits([]); setSaleId('');
    void Promise.all([
      api.get<Status>(`/fiscal/${companyId}/configuration`),
      api.get<Option[]>(`/devices/branches/${companyId}`), api.get<Option[]>(`/devices/${companyId}`),
      api.get<RecordRow[]>(`/fiscal/${companyId}/preparations`),
      api.get<{ action: string; created_at: string }[]>(`/fiscal/${companyId}/audit`),
    ]).then(([config, branch, device, prepared, audit]) => {
      if (!current) return;
      setStatus(config.data); if (config.data.settings) {
        const value = config.data.settings;
        setDraft({ environment: value.environment, taxpayer_tin: value.taxpayer_tin, vat_number: value.vat_number,
          branch_id: value.branch_id, register_id: value.register_id, device_id: value.device_id,
          device_serial: value.device_serial, model_name: value.model_name, model_version: value.model_version });
        setTaxes(JSON.stringify(value.taxes, null, 2));
      }
      setBranches(branch.data); setDevices(device.data); setRecords(prepared.data); setAudits(audit.data);
    }).catch(error => { if (current) setNotice(message(error)); });
    return () => { current = false; };
  }, [companyId]);
  function field<K extends keyof Draft>(key: K, value: Draft[K]) { setDraft(previous => ({ ...previous, [key]: value })); }
  async function save() {
    setBusy(true); setNotice('');
    try {
      const parsed: unknown = JSON.parse(taxes);
      if (!Array.isArray(parsed)) throw new Error('Tax mappings must be a JSON array.');
      const result = await api.put<Status>(`/fiscal/${companyId}/configuration`, { ...draft, expected_version: status?.version ?? 0, taxes: parsed });
      setStatus(result.data); setNotice('Draft saved. Fiscal submission remains disabled.');
      setAudits((await api.get(`/fiscal/${companyId}/audit`)).data);
    } catch (error) { setNotice(error instanceof SyntaxError ? 'Invalid tax mapping JSON.' : message(error)); }
    finally { setBusy(false); }
  }
  async function prepare() {
    setBusy(true); setNotice('');
    try {
      await api.post(`/fiscal/${companyId}/preparations/${encodeURIComponent(saleId)}`);
      setRecords((await api.get(`/fiscal/${companyId}/preparations`)).data);
      setAudits((await api.get(`/fiscal/${companyId}/audit`)).data);
      setNotice('Immutable source review saved. Not a fiscal receipt; nothing transmitted.');
    } catch (error) { setNotice(message(error)); }
    finally { setBusy(false); }
  }
  return <section className="settings-card">
    <h3>Fiscalisation · preparation</h3>
    <p role="status">Not ZIMRA approved · Live and test submissions disabled · Remote status not checked</p>
    {notice && <p role="status">{notice}</p>}
    {status && <>
      <div className="settings-grid">
        <label>Environment<select value={draft.environment} onChange={event => field('environment', event.target.value as Draft['environment'])}><option value="test">Test (uncommissioned)</option><option value="production">Production (disabled)</option></select></label>
        <label>Taxpayer TIN<input maxLength={10} value={draft.taxpayer_tin} onChange={event => field('taxpayer_tin', event.target.value)} /></label>
        <label>VAT number (optional)<input maxLength={9} value={draft.vat_number || ''} onChange={event => field('vat_number', event.target.value || null)} /></label>
        <label>Branch<select value={draft.branch_id} onChange={event => { field('branch_id', event.target.value); field('register_id', ''); }}><option value="">Select branch</option>{branches.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
        <label>Register<select value={draft.register_id} onChange={event => field('register_id', event.target.value)}><option value="">Select register</option>{devices.filter(row => row.branch_id === draft.branch_id).map(row => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
        <label>FDMS device ID<input type="number" min="1" value={draft.device_id} onChange={event => field('device_id', Number(event.target.value))} /></label>
        <label>Device serial<input maxLength={20} value={draft.device_serial} onChange={event => field('device_serial', event.target.value)} /></label>
        <label>Registered model<input value={draft.model_name} onChange={event => field('model_name', event.target.value)} /></label>
        <label>Registered model version<input value={draft.model_version} onChange={event => field('model_version', event.target.value)} /></label>
      </div>
      <label>Draft tax mappings (from FDMS configuration; no default rates)<textarea style={{ width: '100%', boxSizing: 'border-box', minHeight: 110 }} value={taxes} onChange={event => setTaxes(event.target.value)} /></label>
      <p>Secrets are provisioned server-side only. No activation keys or private keys are accepted here.</p>
      <button className="settings-primary-button" disabled={busy} onClick={() => void save()}>Save draft configuration</button>
      <h4>Commissioning gates</h4><ul>{status.blockers.map(text => <li key={text}>{text}</li>)}</ul>
      <h4>Source transaction review</h4>
      <label>Sale reference<input value={saleId} onChange={event => setSaleId(event.target.value)} placeholder="Existing sale ID" /></label>
      <button className="settings-secondary-button" disabled={busy || !saleId} onClick={() => void prepare()}>Prepare review snapshot</button>
      <p>Manual review only. Does not issue, sign, backdate or send a fiscal invoice.</p>
      {records.length ? records.map(row => <p key={row.id} style={{ overflowWrap: 'anywhere' }}>{row.sale_id} · Review only · SHA-256 {row.sha256}</p>) : <p>No source review snapshots.</p>}
      <h4>Fiscal audit · latest 50 events</h4>{audits.map((row, index) => <p key={`${row.created_at}-${index}`}>{row.created_at} · {row.action}</p>)}
    </>}
  </section>;
}
