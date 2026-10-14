import unittest
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException

from app.credit.schema import SettlementCreate
from app.credit.service import CreditService
from app.expenses.schema import ExpenseCreate
from app.expenses.service import ExpenseService


class FinancialCurrencyQuoteValidationTests(unittest.TestCase):
    def test_settlement_accepts_current_company_quote_and_legacy_callers(self):
        rate_id = uuid4()
        data = SettlementCreate(
            company_id=uuid4(), receivable_id=uuid4(), branch_id=uuid4(),
            payment_method="cash", payment_currency_code="ZAR",
            currency_config_version=7, exchange_rate_id=rate_id,
            exchange_rate_snapshot="18.5000000000", idempotency_key="settlement-quote-7",
        )
        CreditService.validate_currency_quote(data, {
            "exchange_rate_id": rate_id,
            "exchange_rate_snapshot": Decimal("18.5000000000"),
        }, 7)
        CreditService.validate_currency_quote(
            SettlementCreate(company_id=uuid4(), receivable_id=uuid4(), branch_id=uuid4(),
                             payment_method="cash", idempotency_key="legacy-settle-1"),
            {"exchange_rate_id": uuid4(), "exchange_rate_snapshot": Decimal("1")}, None,
        )

    def test_stale_settlement_configuration_or_rate_is_rejected(self):
        data = SettlementCreate(
            company_id=uuid4(), receivable_id=uuid4(), branch_id=uuid4(),
            payment_method="cash", payment_currency_code="ZAR",
            currency_config_version=7, exchange_rate_id=uuid4(),
            idempotency_key="settlement-stale-7",
        )
        with self.assertRaises(HTTPException) as changed_version:
            CreditService.validate_currency_quote(data, {"exchange_rate_id": data.exchange_rate_id,
                                                         "exchange_rate_snapshot": Decimal("18.5")}, 8)
        self.assertEqual(changed_version.exception.status_code, 409)
        with self.assertRaises(HTTPException) as changed_rate:
            CreditService.validate_currency_quote(data, {"exchange_rate_id": uuid4(),
                                                         "exchange_rate_snapshot": Decimal("19")}, 7)
        self.assertEqual(changed_rate.exception.status_code, 409)

    def test_expense_quote_uses_config_version_and_authoritative_rate_id(self):
        rate_id = uuid4()
        data = ExpenseCreate(
            company_id=uuid4(), category_id=uuid4(), branch_id=uuid4(),
            original_amount="185.00", currency_code="ZAR", payment_method="cash",
            occurred_at=datetime.now(timezone.utc),
            description="Cash purchase", idempotency_key="expense-quote-7",
            currency_config_version=7, exchange_rate_id=rate_id,
        )
        ExpenseService.validate_currency_quote(data, {
            "exchange_rate_id": rate_id,
            "exchange_rate_snapshot": Decimal("18.5000000000"),
        }, 7)
        with self.assertRaises(HTTPException) as changed:
            ExpenseService.validate_currency_quote(data, {
                "exchange_rate_id": uuid4(),
                "exchange_rate_snapshot": Decimal("19"),
            }, 7)
        self.assertEqual(changed.exception.status_code, 409)

    def test_settlement_schema_accepts_tendered_cash_and_rejects_nonpositive_values(self):
        common = {
            "company_id": uuid4(), "receivable_id": uuid4(), "branch_id": uuid4(),
            "payment_method": "cash", "idempotency_key": "settle-tender-01",
        }
        data = SettlementCreate(**common, original_amount="92.50", tendered_amount_original="100.00")
        self.assertEqual(data.tendered_amount_original, Decimal("100.00"))
        with self.assertRaises(ValueError):
            SettlementCreate(**{**common, "idempotency_key": "settle-tender-02"},
                             original_amount="92.50", tendered_amount_original="0")


if __name__ == "__main__":
    unittest.main()
