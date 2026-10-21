"""FDMS v7.2 §§13.1–13.3 canonical messages. No keys or guessed RSA padding.

Cryptographic providers sign/verify these messages using an authorised device key.
Their wire encoding and certificate chain require FDMS conformance testing.
"""
import base64
import hashlib
import re
from datetime import datetime
from typing import Protocol
from .validation import number

COUNTERS = ('SaleByTax', 'SaleTaxByTax', 'CreditNoteByTax', 'CreditNoteTaxByTax',
            'DebitNoteByTax', 'DebitNoteTaxByTax', 'BalanceByMoneyType')
MONEY = ('Cash', 'Card', 'MobileWallet', 'Coupon', 'Credit', 'BankTransfer', 'Other')


def local_time(value: str) -> datetime:
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}', value):
        raise ValueError('FDMS requires an explicit second-precision local timestamp')
    return datetime.strptime(value, '%Y-%m-%dT%H:%M:%S')


def positive_integer(value):
    if type(value) is not int or value <= 0 or value > 2147483647:
        raise ValueError('Positive Int32 required')
    return str(value)


def cents(value):
    amount = number(value)
    if abs(amount) >= 10 ** 19 or amount != amount.quantize(number('0.01')):
        raise ValueError('Amount must fit Decimal(21,2), without rounding')
    return str(int(amount * 100))


def percent(value):
    if value is None:
        return ''
    rate = number(value)
    if rate < 0 or rate >= 1000 or rate != rate.quantize(number('0.01')):
        raise ValueError('Percentage must fit Decimal(5,2)')
    return format(rate, '.2f')


def binary(value: str, length=None):
    try:
        result = base64.b64decode(value, validate=True)
    except (TypeError, ValueError):
        raise ValueError('Invalid base64') from None
    if not result or (length is not None and len(result) != length):
        raise ValueError('Invalid binary length')
    return result


def receipt_message(device_id: int, receipt: dict, previous_hash: str | None) -> bytes:
    kind, currency = receipt['receiptType'], receipt['receiptCurrency']
    if kind not in ('FiscalInvoice', 'CreditNote', 'DebitNote') or not re.fullmatch('[A-Z]{3}', currency):
        raise ValueError('Invalid receipt type/currency')
    local_time(receipt['receiptDate'])
    positive_integer(receipt['receiptCounter'])
    if receipt['receiptCounter'] == 1:
        if previous_hash is not None:
            raise ValueError('First receipt of day must not chain previous day hash')
    else:
        binary(previous_hash, 32)
    taxes = sorted(receipt['receiptTaxes'], key=lambda row: (row['taxID'], row.get('taxCode') or ''))
    text = positive_integer(device_id) + kind.upper() + currency + positive_integer(receipt['receiptGlobalNo'])
    text += receipt['receiptDate'] + cents(receipt['receiptTotal'])
    for row in taxes:
        code = row.get('taxCode') or ''
        if not re.fullmatch('[A-Za-z0-9]{0,3}', code):
            raise ValueError('Invalid tax code')
        if type(row['taxID']) is not int or row['taxID'] < 0:
            raise ValueError('Invalid tax ID')
        text += code + percent(row.get('taxPercent')) + cents(row['taxAmount']) + cents(row['salesAmountWithTax'])
    return (text + (previous_hash or '')).encode('utf-8')


def counter_message(counters: list[dict]) -> str:
    def key(row):
        kind = row['fiscalCounterType']
        return (COUNTERS.index(kind), row['fiscalCounterCurrency'],
                MONEY.index(row['fiscalCounterMoneyType']) if kind == 'BalanceByMoneyType' else row['fiscalCounterTaxID'])
    text = ''
    seen = set()
    for row in sorted(counters, key=key):
        identity = key(row)
        if identity in seen or abs(number(row['fiscalCounterValue'])) >= 10**17:
            raise ValueError('Duplicate counter or value outside Decimal(19,2)')
        seen.add(identity)
        if number(row['fiscalCounterValue']) == 0:
            continue
        currency = row['fiscalCounterCurrency']
        if not re.fullmatch('[A-Z]{3}', currency):
            raise ValueError('Invalid counter currency')
        suffix = row['fiscalCounterMoneyType'].upper() if row['fiscalCounterType'] == 'BalanceByMoneyType' else percent(row.get('fiscalCounterTaxPercent'))
        text += row['fiscalCounterType'].upper() + currency + suffix + cents(row['fiscalCounterValue'])
    return text


def day_message(device_id, day_no, opened: str, counters: list[dict]) -> bytes:
    date = local_time(opened).date().isoformat()
    return (positive_integer(device_id) + positive_integer(day_no) + date + counter_message(counters)).encode()


def receipt_server_message(receipt: dict, response: dict) -> bytes:
    local_time(response['serverDate'])
    receipt_id = response['receiptID']
    if type(receipt_id) is not int or receipt_id <= 0:
        raise ValueError('Invalid FDMS receipt ID')
    signature = receipt['receiptDeviceSignature']['signature']
    binary(signature)
    return (signature + str(receipt_id) + response['serverDate']).encode()


def sha256(message: bytes) -> str:
    return base64.b64encode(hashlib.sha256(message).digest()).decode()


class SignatureProvider(Protocol):
    """Tenant-bound keystore/HSM; never return a private key to caller."""
    def sign(self, message: bytes) -> bytes: ...
    def verify(self, message: bytes, signature: bytes) -> bool: ...


def sign_message(message: bytes, provider: SignatureProvider) -> dict:
    signature = provider.sign(message)
    if not isinstance(signature, bytes) or not signature or not provider.verify(message, signature):
        raise ValueError('Device signature failed local verification')
    return {'hash': sha256(message), 'signature': base64.b64encode(signature).decode()}


def verify_server_receipt(receipt: dict, response: dict, trusted_verifier) -> None:
    """trusted_verifier must bind thumbprint to a verified FDMS certificate chain."""
    data = response['receiptServerSignature']
    binary(data['certificateThumbprint'], 20)
    message = receipt_server_message(receipt, response)
    if data['hash'] != sha256(message) or not trusted_verifier(message, binary(data['signature']), data['certificateThumbprint']):
        raise ValueError('FDMS acknowledgement signature is not trusted')
