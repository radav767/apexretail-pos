"""FDMS v7.2 §6: per-currency counters, separate from sales/shift calculations."""
from collections import defaultdict
from decimal import Decimal
from .validation import number
from .signatures import percent


def fiscal_counters(receipts: list[dict]) -> list[dict]:
    totals = defaultdict(Decimal)
    for receipt in receipts:
        name = {'FiscalInvoice': 'Sale', 'CreditNote': 'CreditNote', 'DebitNote': 'DebitNote'}[receipt['receiptType']]
        currency = receipt['receiptCurrency']
        for tax in receipt['receiptTaxes']:
            key = (currency, tax['taxID'], percent(tax['taxPercent']) if tax.get('taxPercent') is not None else None)
            totals[(name + 'ByTax', *key)] += number(tax['salesAmountWithTax'])
            totals[(name + 'TaxByTax', *key)] += number(tax['taxAmount'])
        for payment in receipt['receiptPayments']:
            totals[('BalanceByMoneyType', currency, payment['moneyTypeCode'], None)] += number(payment['paymentAmount'])
    result = []
    for (kind, currency, identity, rate), value in totals.items():
        if not value:
            continue
        row = {'fiscalCounterType': kind, 'fiscalCounterCurrency': currency, 'fiscalCounterValue': format(value, '.2f')}
        if kind == 'BalanceByMoneyType':
            row['fiscalCounterMoneyType'] = identity
        else:
            row['fiscalCounterTaxID'] = identity
            if rate is not None:
                row['fiscalCounterTaxPercent'] = rate
        result.append(row)
    return result
