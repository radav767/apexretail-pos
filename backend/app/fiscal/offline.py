"""FDMS v7.2 closed-day offline export; no upload or queue deletion.

Conservative subset: only a complete single closed day. Header-only/open-day
uploads and automatic split sequencing await clarification of conflicting §2/§4 text.
"""
import base64
import hashlib
import json
from decimal import Decimal
from .signatures import local_time, positive_integer, binary, receipt_message, day_message, sha256
from .validation import number
from .counters import fiscal_counters

DECIMALS = {'receiptTotal', 'receiptLinePrice', 'receiptLineQuantity', 'receiptLineTotal',
            'taxPercent', 'taxAmount', 'salesAmountWithTax', 'paymentAmount',
            'fiscalCounterTaxPercent', 'fiscalCounterValue'}


def wire_json(value, key=None):
    """Exact decimal JSON numbers, never float conversion or quoted money."""
    if key in DECIMALS and value is not None:
        return format(number(value), 'f')
    if isinstance(value, dict):
        return '{' + ','.join(json.dumps(str(k)) + ':' + wire_json(v, k) for k, v in value.items()) + '}'
    if isinstance(value, list):
        return '[' + ','.join(wire_json(v) for v in value) + ']'
    if isinstance(value, Decimal):
        raise ValueError('Undeclared decimal field')
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def closed_day_file(*, mode, device_id, day_no, opened, closed, receipts, footer, sequence, status, device_verifier):
    if mode != 'Offline' or status != 'FiscalDayClosed':
        raise ValueError('Offline file requires configured Offline mode and a locally closed day')
    positive_integer(device_id); positive_integer(day_no); positive_integer(sequence)
    start, end = local_time(opened), local_time(closed)
    if end < start:
        raise ValueError('Invalid fiscal day interval')
    previous_global = None
    previous_hash = None
    seen = set()
    for counter, receipt in enumerate(receipts, 1):
        stamp = local_time(receipt['receiptDate'])
        if receipt['receiptCounter'] != counter or not start <= stamp <= end or receipt['invoiceNo'] in seen:
            raise ValueError('File contains gaps, duplicates or receipts outside fiscal day')
        seen.add(receipt['invoiceNo'])
        positive_integer(receipt['receiptGlobalNo'])
        if previous_global is not None and receipt['receiptGlobalNo'] != previous_global + 1:
            raise ValueError('Receipt global sequence has a gap')
        previous_global = receipt['receiptGlobalNo']
        signature = receipt['receiptDeviceSignature']
        message = receipt_message(device_id, receipt, previous_hash)
        if signature['hash'] != sha256(message) or not device_verifier(message, binary(signature['signature'])):
            raise ValueError('Receipt signature/hash chain is invalid')
        previous_hash = signature['hash']
    expected = fiscal_counters(receipts)
    if footer.get('fiscalDayCounters') != expected or footer.get('receiptCounter') != len(receipts) or footer.get('fiscalDayClosed') != closed:
        raise ValueError('Footer does not match issued receipts')
    signature = footer['fiscalDayDeviceSignature']; message = day_message(device_id, day_no, opened, expected)
    if signature['hash'] != sha256(message) or not device_verifier(message, binary(signature['signature'])):
        raise ValueError('Fiscal closing signature is invalid')
    document = {'header': {'deviceID': device_id, 'fiscalDayNo': day_no, 'fiscalDayOpened': opened, 'fileSequence': sequence},
                'content': {'receipts': receipts}, 'footer': footer}
    raw = wire_json(document).encode('utf-8')
    if len(raw) >= 3_000_000:
        raise ValueError('File size requires reviewed sequential splitting; no receipts discarded')
    return {'file': base64.b64encode(raw).decode(), 'sha256': hashlib.sha256(raw).hexdigest(),
            'bytes': len(raw), 'submitted': False}
