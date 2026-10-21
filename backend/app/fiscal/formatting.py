"""FDMS v7.2 §§10–11 field layout for REVIEW, not a certified print path."""
from html import escape
import re
from urllib.parse import urlsplit
from .signatures import local_time
from .validation import number


def verification_url(qr_url, device_id, receipt_date, global_no, qr_data):
    """Assemble documented QR URL from verified getConfig and QR-data inputs.

    Does not derive QR data: MD5 input wording needs a paired signature/QR fixture.
    """
    parsed = urlsplit(qr_url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Invalid FDMS-provided verification URL')
    if type(device_id) is not int or type(global_no) is not int or not 0 < device_id < 10**10 or not 0 < global_no < 10**10:
        raise ValueError('Invalid QR identification')
    if not re.fullmatch('[A-F0-9]{16}', qr_data):
        raise ValueError('Verified QR data must contain sixteen uppercase hexadecimal characters')
    date = local_time(receipt_date).strftime('%d%m%Y')
    return qr_url.rstrip('/') + '/' + str(device_id).zfill(10) + date + str(global_no).zfill(10) + qr_data


def receipt_preview(receipt, config, *, device_id, day_no, paper='80mm'):
    if paper not in ('58mm', '80mm', 'A4'):
        raise ValueError('Unsupported paper')
    if paper != 'A4' and not receipt['receiptLinesTaxInclusive']:
        raise ValueError('Receipt48 is documented for tax-inclusive lines; use A4 for tax-exclusive preview')
    def text(value): return escape(str(value if value is not None else ''))
    def details(value): return text(', '.join(str(v) for v in value.values() if v)) if isinstance(value, dict) else text(value)
    title = {'FiscalInvoice': 'Fiscal tax invoice' if config.get('vatNumber') else 'Fiscal invoice',
             'CreditNote': 'Credit note', 'DebitNote': 'Debit note'}[receipt['receiptType']]
    width = '210mm' if paper == 'A4' else paper
    page_size = 'A4' if paper == 'A4' else 'auto'
    html = f'<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Fiscal review</title><style>body{{font-family:monospace;max-width:{width};margin:auto;padding:8px;box-sizing:border-box;overflow-wrap:anywhere}}table{{width:100%;border-collapse:collapse;table-layout:fixed}}td,th{{text-align:left;vertical-align:top;overflow-wrap:anywhere}}.notice{{border:2px solid;padding:8px}}@media print{{@page{{size:{page_size};margin:0}}}}</style></head><body>'
    html += '<p class="notice">TEST / REVIEW ONLY — NOT A VALID FISCAL DOCUMENT — NOT ZIMRA APPROVED</p>'
    html += f'<h2>{text(config["taxPayerName"])}</h2><p>TIN {text(config["taxPayerTIN"])}<br>VAT {text(config.get("vatNumber"))}<br>{text(config["deviceBranchName"])}<br>{details(config["deviceBranchAddress"])}<br>{details(config.get("deviceBranchContacts", {}))}</p>'
    html += f'<h3>{title}</h3><p>Invoice {text(receipt["invoiceNo"])}<br>Counter / Global {text(receipt["receiptCounter"])} / {text(receipt["receiptGlobalNo"])}<br>Fiscal day {text(day_no)}<br>Serial {text(config["deviceSerialNo"])}<br>Device {text(device_id)}<br>{text(receipt["receiptDate"])}</p>'
    if receipt.get('buyerData'):
        html += '<h4>Buyer</h4>' + ''.join(f'<p>{details(value)}</p>' for value in receipt['buyerData'].values())
    if receipt.get('creditDebitNote'):
        html += '<p>Original fiscal reference: ' + details(receipt['creditDebitNote']) + '</p>'
    html += '<table><thead><tr><th>Item</th><th>Qty / Price</th><th>Total</th></tr></thead><tbody>'
    for line in receipt['receiptLines']:
        html += f'<tr><td>{text(line["receiptLineName"])} {text(line.get("taxCode"))}</td><td>{text(line["receiptLineQuantity"])} × {text(line.get("receiptLinePrice"))}</td><td>{text(line["receiptLineTotal"])}</td></tr>'
    html += f'</tbody></table><h3>{text(receipt["receiptCurrency"])} {text(receipt["receiptTotal"])}</h3>'
    for row in receipt['receiptPayments']:
        html += f'<p>{text(row["moneyTypeCode"])} {text(row["paymentAmount"])}</p>'
    quantity = sum(abs(number(line['receiptLineQuantity'])) for line in receipt['receiptLines'] if line['receiptLineType'] == 'Sale')
    html += f'<p>Number of items {text(quantity)}</p>'
    if config.get('vatNumber'):
        html += '<h4>Taxes</h4><table><tr><th>Code / %</th><th>Net</th><th>Tax</th><th>Gross</th></tr>'
        for row in receipt['receiptTaxes']:
            net = number(row['salesAmountWithTax']) - number(row['taxAmount'])
            html += f'<tr><td>{text(row.get("taxCode"))} {text(row.get("taxPercent", "Exempt"))}</td><td>{text(net)}</td><td>{text(row["taxAmount"])}</td><td>{text(row["salesAmountWithTax"])}</td></tr>'
        html += '</table>'
    html += f'<p>{text(receipt.get("receiptNotes"))}</p><p>Fiscal verification code / QR withheld until commissioned and verified.</p></body></html>'
    return html
