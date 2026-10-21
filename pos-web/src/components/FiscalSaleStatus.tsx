import { useEffect, useState } from 'react';
import { api } from '../api/client';
type FiscalStatus = { configured: boolean; status: string; environment: string; certified: boolean; submitted: boolean | null };

export default function FiscalSaleStatus({ companyId, saleId }: { companyId: string; saleId: string }) {
  const [status, setStatus] = useState<FiscalStatus | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  useEffect(() => {
    let current = true;
    setStatus(null); setUnavailable(false);
    void api.get<FiscalStatus>(`/fiscal/${encodeURIComponent(companyId)}/sales/${encodeURIComponent(saleId)}/status`)
      .then(response => { if (current) setStatus(response.data); })
      .catch(() => { if (current) setUnavailable(true); });
    return () => { current = false; };
  }, [companyId, saleId]);
  if (unavailable) return <p role="status">Fiscal status unavailable. This does not change the sale status.</p>;
  if (!status?.configured) return null;
  return <p role="status">Fiscalisation · {status.environment === 'test' ? 'TEST ONLY · ' : ''}
    {status.status === 'acknowledged_test_validation_unknown' ? 'Acknowledged in test; validity not confirmed'
      : status.status === 'test_receipt_queued' ? 'Queued for test review'
      : status.status.includes('requires_review') ? 'Submission requires reconciliation; do not create a replacement'
      : 'Not fiscalised'}
  </p>;
}
