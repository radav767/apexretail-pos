"""Applied split amounts and physical original cash for target shift only."""
from sqlalchemy import text,select
from fastapi import HTTPException
from app.models import CashierShiftCurrencySnapshot

SQL=text('''WITH paid AS (SELECT t.* FROM sale_tenders t JOIN sales s ON s.id=t.sale_id AND s.company_id=t.company_id
 WHERE s.shift_id=:shift AND s.payment_method='split'), returned AS (
 SELECT a.*,t.currency_code FROM sale_tender_refunds a JOIN sales s ON s.id=a.refund_sale_id AND s.company_id=a.company_id
 JOIN sale_tenders t ON t.id=a.tender_id AND t.company_id=a.company_id WHERE s.shift_id=:shift AND a.kind='paid_refund' AND t.method='cash')
 SELECT (SELECT COALESCE(sum(tendered_original-change_original),0) FROM paid WHERE method='cash' AND (CAST(:code AS text) IS NULL OR currency_code=:code)) cash_original,
 (SELECT COALESCE(sum(amount_original),0) FROM returned WHERE CAST(:code AS text) IS NULL OR currency_code=:code) cash_refund_original,
 (SELECT COALESCE(sum(applied_base),0) FROM paid WHERE method='cash') cash_base,
 (SELECT COALESCE(sum(applied_base),0) FROM paid WHERE method='credit') credit_base,
 (SELECT COALESCE(sum(amount_base),0) FROM returned) cash_refund_base''')

async def activity(db,shift,code=None):return (await db.execute(SQL,{'shift':shift,'code':code})).mappings().one()

async def require_cash_snapshots(db,shift,codes):
    if not shift or not codes:return
    known=dict((await db.execute(select(CashierShiftCurrencySnapshot.currency_code,CashierShiftCurrencySnapshot.decimal_places_snapshot).where(CashierShiftCurrencySnapshot.shift_id==shift.id,CashierShiftCurrencySnapshot.cash_accepted_snapshot.is_(True)))).all())
    if any(code not in known or known[code]!=places for code,places in codes.items()):raise HTTPException(409,'Split cash currency/precision has no matching cash-enabled target shift snapshot; retain for review')
