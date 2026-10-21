"""Documented local validations; FDMS itself must still validate each receipt."""
import calendar
import re
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from .signatures import local_time, positive_integer, cents, percent
from .validation import number, tax_amount, validate_receipt_totals


def validate_receipt(receipt, config, opened, *, allowed_currencies, previous=None,
                     original=None, original_receipt_id=None, already_credited='0'):
    validate_receipt_totals(receipt)
    stamp = local_time(receipt['receiptDate'])
    beginning = local_time(opened)
    if stamp < beginning or stamp > beginning + timedelta(hours=config['taxPayerDayMaxHrs']):
        raise ValueError('Receipt outside configured fiscal day')
    if previous and stamp < local_time(previous['receiptDate']):
        raise ValueError('Receipt precedes previous original timestamp')
    if receipt['receiptCurrency'] not in allowed_currencies:
        raise ValueError('Currency has not been verified for this device')
    if not isinstance(receipt.get('invoiceNo'), str) or not 1 <= len(receipt['invoiceNo']) <= 50:
        raise ValueError('Invoice number is required')
    positive_integer(receipt['receiptCounter']); positive_integer(receipt['receiptGlobalNo'])
    if receipt.get('receiptPrintForm', 'Receipt48') not in ('Receipt48', 'InvoiceA4'):
        raise ValueError('Unsupported receipt print form')
    buyer = receipt.get('buyerData')
    if buyer:
        if not buyer.get('buyerRegisterName') or not re.fullmatch('[0-9]{10}', buyer.get('buyerTIN', '')):
            raise ValueError('Buyer block requires registered name and TIN; never fabricate TIN')
        if not buyer.get('buyerAddress') or not buyer.get('buyerContacts'):
            raise ValueError('Captured buyer details require address and contact information')
    kind = receipt['receiptType']
    if kind != 'FiscalInvoice':
        if original is None or original_receipt_id is None or receipt['creditDebitNote'].get('receiptID') != original_receipt_id:
            raise ValueError('Verified original fiscal receipt is required')
        if original['receiptCurrency'] != receipt['receiptCurrency']:
            raise ValueError('Note currency differs from original invoice')
        original_time = local_time(original['receiptDate'])
        next_year = original_time.year + 1
        limit = original_time.replace(year=next_year, day=min(original_time.day, calendar.monthrange(next_year, original_time.month)[1]))
        if stamp < original_time or stamp > limit:
            raise ValueError('Note is outside original invoice twelve-month period')
        if kind == 'CreditNote' and abs(number(receipt['receiptTotal'])) + number(already_credited) > number(original['receiptTotal']):
            raise ValueError('Cumulative credit exceeds original invoice')
    groups = {}
    for line in receipt['receiptLines']:
        if line.get('receiptLineType') not in ('Sale', 'Discount') or not isinstance(line.get('receiptLineName'), str) or not 1 <= len(line['receiptLineName']) <= 200:
            raise ValueError('Invalid line type/name')
        quantity = number(line['receiptLineQuantity'])
        if quantity != quantity.quantize(Decimal('.000001')) or quantity >= 10 ** 19:
            raise ValueError('Quantity must fit Decimal(25,6)')
        total = number(line['receiptLineTotal']); cents(total)
        if 'receiptLinePrice' in line:
            price = number(line['receiptLinePrice'])
            if price != price.quantize(Decimal('.000001')) or abs(price) >= 10 ** 19:
                raise ValueError('Price must fit Decimal(25,6)')
            if (price * quantity).quantize(Decimal('.01'), rounding=ROUND_HALF_UP) != total:
                raise ValueError('Price, quantity and line total mismatch')
            if line['receiptLineType'] == 'Sale' and ((kind == 'CreditNote' and price >= 0) or (kind != 'CreditNote' and price <= 0)):
                raise ValueError('Sale line price has invalid sign')
            if kind == 'FiscalInvoice' and line['receiptLineType'] == 'Discount' and price >= 0:
                raise ValueError('Discount line must be negative')
        rate = line.get('taxPercent'); percent(rate)
        key = (line['taxID'], line.get('taxCode') or '', percent(rate))
        available = [tax for tax in config['applicableTaxes'] if tax['taxID'] == line['taxID'] and percent(tax.get('taxPercent')) == percent(rate)
                     and tax['taxValidFrom'] <= stamp.date().isoformat() and (not tax.get('taxValidTill') or stamp.date().isoformat() <= tax['taxValidTill'])]
        if not available:
            raise ValueError('Tax identity/rate/date not in FDMS configuration')
        if not config.get('vatNumber') and rate is not None and number(rate) > 0 and original is None:
            raise ValueError('Non-VAT taxpayer cannot issue new VAT invoice')
        hs = line.get('receiptLineHSCode')
        allowed_lengths = (8,) if config.get('vatNumber') and (rate is None or number(rate) == 0) else (4, 8)
        if (config.get('vatNumber') and not hs) or (hs is not None and (not re.fullmatch('[0-9]+', hs) or len(hs) not in allowed_lengths)):
            raise ValueError('HS code missing or incompatible with taxpayer/tax type')
        groups[key] = groups.get(key, Decimal(0)) + total
    codes = [bool(line.get('taxCode')) for line in receipt['receiptLines']]
    if any(codes) and not all(codes):
        raise ValueError('Tax codes must be present on every line or none')
    original_taxes = {(t['taxID'], percent(t.get('taxPercent'))) for t in original['receiptTaxes']} if original else None
    observed = set()
    for tax in receipt['receiptTaxes']:
        key = (tax['taxID'], tax.get('taxCode') or '', percent(tax.get('taxPercent')))
        if key in observed or key not in groups:
            raise ValueError('Duplicate or unmatched tax summary')
        observed.add(key)
        if original_taxes is not None and (tax['taxID'], percent(tax.get('taxPercent'))) not in original_taxes:
            raise ValueError('Note introduces a tax absent from original invoice')
        expected = tax_amount(groups[key], tax.get('taxPercent'), inclusive=receipt['receiptLinesTaxInclusive'])
        if number(tax['taxAmount']) != expected:
            raise ValueError('Tax total mismatch; rounding convention needs conformance testing')
        gross = groups[key] if receipt['receiptLinesTaxInclusive'] else groups[key] + expected
        if number(tax['salesAmountWithTax']) != gross:
            raise ValueError('Tax-inclusive sales total mismatch')
    if observed != set(groups):
        raise ValueError('Missing tax summary')
