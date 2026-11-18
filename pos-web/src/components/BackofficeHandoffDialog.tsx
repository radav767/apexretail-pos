import { useEffect, useRef, useState } from 'react';

type Props = { open: boolean; onClose: () => void; authenticate: (email: string, password: string) => Promise<boolean> };
export default function BackofficeHandoffDialog({ open, onClose, authenticate }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [email, setEmail] = useState(''); const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  useEffect(() => {
    if (open) dialog.current?.showModal();
    else { dialog.current?.close(); setPassword(''); setEmail(''); setError(''); }
  }, [open]);
  return <dialog ref={dialog} aria-labelledby="backoffice-auth-title" onCancel={event => { event.preventDefault(); if (!busy) onClose(); }}
    style={{ background: '#fff', color: '#172033', border: '1px solid #d0d5dd', borderRadius: 12, padding: 24, maxWidth: 440, width: '90vw' }}>
    <form onSubmit={async event => {
      event.preventDefault(); setBusy(true); setError('');
      try { if (await authenticate(email, password)) onClose(); else setError('Owner authentication failed for this business, or the connection is unavailable.'); }
      finally { setPassword(''); setBusy(false); }
    }}>
      <h2 id="backoffice-auth-title">Open Backoffice</h2>
      <p>An owner or administrator must authenticate for this business. Cashier access stays unchanged.</p>
      <label>Email<input type="email" autoComplete="username" required autoFocus value={email} onChange={event => setEmail(event.target.value)} /></label>
      <label>Password<input type="password" autoComplete="current-password" required value={password} onChange={event => setPassword(event.target.value)} /></label>
      {error && <p role="alert">{error}</p>}
      <button type="submit" disabled={busy}>{busy ? 'Authenticating...' : 'Open with owner authentication'}</button>
      <button type="button" disabled={busy} onClick={onClose}>Cancel</button>
    </form>
  </dialog>;
}
