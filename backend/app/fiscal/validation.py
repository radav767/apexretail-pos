"""Local preflight helpers, NOT FDMS approval or a replacement sales tax engine.

    Based on FDMS v7.2 sections 4.7 and 8.2.1. Full signed-payload validation
    additionally requires getConfig, counters, signature chain and onboarding.
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal('0.01')


def number(value):
    try:
        result = Decimal(str(value))
    except (ValueError, InvalidOperation):
        raise ValueError('Invalid decimal') from None
    if not result.is_finite():
        raise ValueError('Non-finite decimal')
    return result


def tax_amount(amount, percent, *, inclusive: bool):
    """Explicit caller-supplied rate; exempt=None is not zero-rated=0.

    Rounding here is for preparation diagnostics only, pending FDMS test vectors.
    Existing transaction totals are never recomputed or updated by this helper.
    """
    value = number(amount)
    if percent is None:
        return Decimal('0.00')
    rate = number(percent)
    if rate < 0 or rate > 100:
        raise ValueError('Invalid percentage')
    rate /= 100
    return (value * rate / (1 + rate) if inclusive else value * rate).quantize(CENT, rounding=ROUND_HALF_UP)


def validate_tax_mapping(mapping, receipt_date, percent):
    """Check draft mapping validity, without claiming it is verified by FDMS."""
    if receipt_date.tzinfo is None:
        raise ValueError('Original timestamp must be timezone-aware before FDMS local-time conversion')
    if receipt_date < mapping.valid_from or (mapping.valid_till and receipt_date > mapping.valid_till):
        raise ValueError('Tax mapping is outside its validity period')
    if (mapping.percent is None) != (percent is None) or (percent is not None and number(percent) != mapping.percent):
        raise ValueError('Tax mapping percentage differs from transaction snapshot')


def validate_receipt_totals(receipt: dict) -> None:
    """Partial structural/totals preflight only; never returns 'fiscalised'."""
    kind = receipt.get('receiptType')
    if kind not in ('FiscalInvoice', 'CreditNote', 'DebitNote'):
        raise ValueError('Unsupported receipt type')
    lines, taxes, payments = (receipt.get(k) for k in ('receiptLines', 'receiptTaxes', 'receiptPayments'))
    if not lines or not taxes or not payments:
        raise ValueError('Lines, taxes and payments are required')
    if type(receipt.get('receiptLinesTaxInclusive')) is not bool:
        raise ValueError('Explicit tax-inclusive flag required')
    total = number(receipt.get('receiptTotal'))
    if total != total.quantize(CENT):
        raise ValueError('Receipt total must have at most two decimal places')
    credit = kind == 'CreditNote'
    if (credit and total > 0) or (not credit and total < 0):
        raise ValueError('Invalid receipt total sign')
    if kind != 'FiscalInvoice':
        ref = receipt.get('creditDebitNote') or {}
        if not receipt.get('receiptNotes') or not (ref.get('receiptID') or all(ref.get(k) for k in ('deviceID', 'receiptGlobalNo', 'fiscalDayNo'))):
            raise ValueError('Credit/debit note requires original fiscal reference and reason')
    elif receipt.get('creditDebitNote'):
        raise ValueError('Invoice cannot reference credited receipt')
    for i, line in enumerate(lines, 1):
        if line.get('receiptLineNo') != i or number(line.get('receiptLineQuantity')) <= 0:
            raise ValueError('Sequential lines and positive quantities required')
        number(line.get('receiptLineTotal'))
    for payment in payments:
        if payment.get('moneyTypeCode') not in ('Cash', 'Card', 'MobileWallet', 'Coupon', 'Credit', 'BankTransfer', 'Other'):
            raise ValueError('Invalid payment method')
        amount = number(payment.get('paymentAmount'))
        if (credit and amount > 0) or (not credit and amount < 0):
            raise ValueError('Invalid payment sign')
    line_sum = sum(number(line['receiptLineTotal']) for line in lines)
    if not receipt['receiptLinesTaxInclusive']:
        line_sum += sum(number(tax.get('taxAmount')) for tax in taxes)
    if total != line_sum or total != sum(number(t.get('salesAmountWithTax')) for t in taxes) or total != sum(number(p['paymentAmount']) for p in payments):
        raise ValueError('Receipt lines, taxes, payments and total do not reconcile')
