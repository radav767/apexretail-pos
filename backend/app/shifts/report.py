from html import escape


def _money(value, code: str, symbol: str) -> str:
    return f"{symbol}{value or 0} {code}"


def report_lines(report: dict) -> list[str]:
    summary = report["summary"]
    base_code = summary.get("base_currency_code") or "BASE"
    lines = [
        report["business_name"],
        f'{report["shop_name"]} / {report["branch_name"]}',
        f'Register: {report["register_name"]}',
        f'Cashier: {report["cashier_name"]}',
        f'Shift: {report["shift_number"]}',
        f'Opened: {report["opened_at"]}',
        f'Closed: {report["closed_at"]}',
        "-" * 32,
        f'Gross sales: {summary.get("gross_sales_base") or 0} {base_code}',
        f'Discounts: {summary.get("discounts_base") or 0} {base_code}',
        f'Refunds: {summary.get("refunds_base") or 0} {base_code}',
        f'Net sales: {summary.get("net_sales_base") or 0} {base_code}',
        f'Cash: {summary.get("cash_sales_base") or 0} {base_code}',
        f'Card: {summary.get("card_sales_base") or 0} {base_code}',
        f'Mobile: {summary.get("mobile_sales_base") or 0} {base_code}',
        f'Credit: {summary.get("credit_sales_base") or 0} {base_code}',
        f'Cash in: {summary.get("cash_in_base") or 0} {base_code}',
        f'Cash out: {summary.get("cash_out_base") or 0} {base_code}',
        "-" * 32,
    ]
    if report.get("tips"):
        lines.append("TIPS (separate from sales)")
        for row in report["tips"].get("totals", []):
            lines.append(f'{row["kind"]} / {row["method"]} / {row["policy"]}: {row["amount"]} {row["currency"]}')
    for row in report["currencies"]:
        code, symbol = row["currency_code"], row["symbol"]
        lines.extend([
            f'{code} ({symbol})',
            f' Opening: {_money(row["opening_float"], code, symbol)}',
            f' Cash sales: {_money(row["cash_sales"], code, symbol)}',
            f' Cash refunds: {_money(row["cash_refunds"], code, symbol)}',
            f' Settlements: {_money(row["cash_settlements"], code, symbol)}',
            f' Cash in/out: {_money(row["cash_in"], code, symbol)} / {_money(row["cash_out"], code, symbol)}',
            f' Expected: {_money(row["expected_cash"], code, symbol)}',
            f' Counted: {_money(row["counted_cash"], code, symbol)}',
            f' Variance: {_money(row["variance"], code, symbol)}',
        ])
    lines.extend([
        "-" * 32,
        f'Closed by: {report["closing_user_name"] or "Unknown"}',
        f'Report generated: {report["report_generated_at"]}',
    ])
    return lines


def thermal_html(report: dict, width: str) -> str:
    millimeters = "58mm" if width == "58mm" else "80mm"
    body = "\n".join(escape(line) for line in report_lines(report))
    return f'''<!doctype html><html><head><meta charset="utf-8"><title>{escape(report["shift_number"])}</title>
<style>@page{{size:{millimeters} auto;margin:3mm}}body{{box-sizing:border-box;width:{millimeters};margin:0;font:11px/1.35 monospace;white-space:pre-wrap;color:#000}}@media print{{button{{display:none}}}}</style></head>
<body>{body}<button type="button" onclick="window.print()">Print Z Report</button></body></html>'''


def simple_pdf(report: dict) -> bytes:
    """Dependency-free, paginated text PDF using WinAnsi currency symbols."""
    lines = report_lines(report)

    def pdf_escape(value: str) -> bytes:
        return (value.encode("cp1252", "replace").replace(b"\\", b"\\\\")
                .replace(b"(", b"\\(").replace(b")", b"\\)"))

    pages = [lines[index:index + 68] for index in range(0, len(lines), 68)] or [[]]
    page_count = len(pages)
    first_page_id = 3
    first_content_id = first_page_id + page_count
    font_id = first_content_id + page_count
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        (f"<< /Type /Pages /Kids [{' '.join(f'{first_page_id + index} 0 R' for index in range(page_count))}] /Count {page_count} >>").encode(),
    ]
    for index in range(page_count):
        objects.append((f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {first_content_id + index} 0 R >>").encode())
    for page_lines in pages:
        stream = [b"BT", b"/F1 9 Tf", b"36 806 Td", b"11 TL"]
        for index, line in enumerate(page_lines):
            if index:
                stream.append(b"T*")
            stream.append(b"(" + pdf_escape(str(line)) + b") Tj")
        stream.append(b"ET")
        content = b"\n".join(stream)
        objects.append(f"<< /Length {len(content)} >>\nstream\n".encode() + content + b"\nendstream")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>")
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(output)); output.extend(f"{number} 0 obj\n".encode()); output.extend(obj); output.extend(b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(f"trailer << /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
    return bytes(output)
