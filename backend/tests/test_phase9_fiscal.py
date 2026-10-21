import copy
from decimal import Decimal
from uuid import uuid4
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
import httpx
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from app.auth.dependencies import AuthActor
from app.auth.security import create_access_token
from app.db.session import get_db
from app.main import app
from app.models import Sale, SaleItem
from app.models.fiscal import FiscalPreparation
from app.fiscal.adapter import UncommissionedFDMSAdapter, FiscalIntegrationUnavailable
from app.fiscal.schema import FiscalSettings, TaxMapping
from app.fiscal.service import FiscalService, digest
from app.fiscal.validation import tax_amount, validate_receipt_totals, validate_tax_mapping
import test_phase7d_operations as fixtures


class FiscalValidationTests(unittest.TestCase):
    def receipt(self):
        return {'receiptType': 'FiscalInvoice', 'receiptLinesTaxInclusive': True, 'receiptTotal': '11.00',
                'receiptLines': [{'receiptLineNo': 1, 'receiptLineQuantity': '1', 'receiptLineTotal': '11.00'}],
                'receiptTaxes': [{'taxAmount': '1.00', 'salesAmountWithTax': '11.00'}],
                'receiptPayments': [{'moneyTypeCode': 'Cash', 'paymentAmount': '11.00'}]}

    def test_explicit_synthetic_tax_rates_and_exempt(self):
        for total, rate, inclusive, expected in [('11', '10', True, '1.00'), ('10', '10', False, '1.00'),
                                                  ('-11', '10', True, '-1.00'), ('11', None, True, '0.00'), ('11', '0', True, '0.00')]:
            with self.subTest(total=total, rate=rate):
                self.assertEqual(tax_amount(total, rate, inclusive=inclusive), Decimal(expected))
        for invalid in ('NaN', 'Infinity', '-1', '101'):
            with self.subTest(rate=invalid), self.assertRaises(ValueError):
                tax_amount('10', invalid, inclusive=True)

    def test_totals_preflight_cash_card_mobile_and_credit_note(self):
        for method in ('Cash', 'Card', 'MobileWallet'):
            value = self.receipt(); value['receiptPayments'][0]['moneyTypeCode'] = method
            validate_receipt_totals(value)
        value = self.receipt(); value['receiptType'] = 'CreditNote'; value['receiptTotal'] = '-11.00'
        value['receiptLines'][0]['receiptLineTotal'] = '-11.00'
        value['receiptTaxes'] = [{'taxAmount': '-1.00', 'salesAmountWithTax': '-11.00'}]
        value['receiptPayments'][0]['paymentAmount'] = '-11.00'
        with self.assertRaises(ValueError): validate_receipt_totals(value)
        value['receiptNotes'] = 'Synthetic return'; value['creditDebitNote'] = {'receiptID': 123}
        validate_receipt_totals(value)

    def test_malformed_totals_quantities_and_payment_signs_are_rejected(self):
        for key, bad in [('receiptTotal', '10.00'), ('receiptTotal', 'NaN'), ('receiptLines', []), ('receiptPayments', []), ('receiptLinesTaxInclusive', 'true')]:
            value = self.receipt(); value[key] = bad
            with self.subTest(key=key), self.assertRaises(ValueError): validate_receipt_totals(value)
        for key, bad in [('receiptLineQuantity', '0'), ('receiptLineNo', 2)]:
            value = self.receipt(); value['receiptLines'][0][key] = bad
            with self.assertRaises(ValueError): validate_receipt_totals(value)
        value = self.receipt(); value['receiptPayments'][0]['paymentAmount'] = '-11'
        with self.assertRaises(ValueError): validate_receipt_totals(value)

    def test_tax_validity_and_no_secret_fields(self):
        with self.assertRaises(ValueError):
            TaxMapping(local_code='A', tax_id=1, valid_from='2026-01-01T00:00:00')
        with self.assertRaises(ValueError):
            FiscalSettings(activation_key='do-not-accept-secrets')

    def test_expired_future_and_exempt_mapping_mismatch(self):
        mapping = TaxMapping(local_code='SYNTHETIC', tax_id=1, percent='10',
                             valid_from='2026-01-01T00:00:00Z', valid_till='2026-12-31T00:00:00Z')
        validate_tax_mapping(mapping, datetime(2026, 10, 21, tzinfo=timezone.utc), '10')
        for timestamp, rate in [(datetime(2027, 1, 1, tzinfo=timezone.utc), '10'),
                                (datetime(2025, 1, 1, tzinfo=timezone.utc), '10'),
                                (datetime(2026, 10, 21, tzinfo=timezone.utc), None)]:
            with self.assertRaises(ValueError): validate_tax_mapping(mapping, timestamp, rate)
        exempt = mapping.model_copy(update={'percent': None})
        validate_tax_mapping(exempt, datetime(2026, 10, 21, tzinfo=timezone.utc), None)
        with self.assertRaises(ValueError): validate_tax_mapping(exempt, datetime(2026, 10, 21, tzinfo=timezone.utc), '0')


class FiscalTests(unittest.IsolatedAsyncioTestCase):
    cleanup = fixtures.Phase7DOperationsTests.cleanup

    async def asyncSetUp(self):
        await fixtures.Phase7DOperationsTests.asyncSetUp(self)
        self.fiscal = FiscalService(self.db, self.owner, self.company.id)

    def settings(self, **changes):
        values = dict(taxpayer_tin='0000000001', branch_id=self.branch.id, register_id=self.device.id,
                      device_id=1, device_serial='SYNTHETIC', model_name='NOT-REGISTERED', model_version='test')
        values.update(changes)
        return FiscalSettings(**values)

    async def test_default_is_uncommissioned_no_submission_and_no_invented_rates(self):
        result = await self.fiscal.configuration()
        self.assertIsNone(result['settings']); self.assertFalse(result['submission_enabled'])
        self.assertEqual(result['certification'], 'not_approved')
        saved = await self.fiscal.save(self.settings())
        self.assertEqual(saved['settings']['taxes'], [])
        self.assertFalse(saved['submission_enabled'])
        for operation, args in [('get_configuration', (1,)), ('get_status', (1,)), ('submit_receipt', (1, {}))]:
            with self.subTest(operation=operation), self.assertRaises(FiscalIntegrationUnavailable):
                await getattr(UncommissionedFDMSAdapter(), operation)(*args)

    async def test_owner_only_business_and_register_isolation(self):
        for actor in (self.waiter, AuthActor('user', self.company.id, 'accountant', user=self.user)):
            with self.assertRaises(HTTPException): FiscalService(self.db, actor, self.company.id)
        with self.assertRaises(HTTPException): FiscalService(self.db, self.owner, uuid4())
        with self.assertRaises(HTTPException): await self.fiscal.save(self.settings(register_id=uuid4()))
        with self.assertRaises(HTTPException): await self.fiscal.save(self.settings(branch_id=uuid4()))
        with self.assertRaises(HTTPException): await self.fiscal.prepare(uuid4())

    async def test_credential_references_masked_tenant_scoped_and_not_accidentally_cleared(self):
        with self.assertRaises(HTTPException):
            await self.fiscal.save(self.settings(credential_reference=f'fiscal/{uuid4()}/key'))
        reference = f'fiscal/{self.company.id}/key-v1'
        result = await self.fiscal.save(self.settings(credential_reference=reference))
        self.assertTrue(result['settings']['credential_configured'])
        self.assertNotIn('credential_reference', result['settings'])
        result = await self.fiscal.save(self.settings(expected_version=1))
        self.assertTrue(result['settings']['credential_configured'])
        result = await self.fiscal.save(self.settings(expected_version=2, credential_reference=None))
        self.assertFalse(result['settings']['credential_configured'])

    async def test_configuration_optimistic_lock_and_audit(self):
        await self.fiscal.save(self.settings())
        with self.assertRaises(HTTPException) as error: await self.fiscal.save(self.settings())
        self.assertEqual(error.exception.status_code, 409)
        await self.fiscal.save(self.settings(expected_version=1))
        audits = await self.fiscal.audits()
        self.assertEqual(len(audits), 2)
        self.assertEqual({a['details']['version'] for a in audits}, {1, 2})
        self.assertEqual(audits[0]['details']['settings']['taxpayer_tin'], '0000000001')
        self.assertNotIn('credential_reference', audits[0]['details']['settings'])

    async def test_source_snapshot_exactly_once_preserves_dates_identity_and_finances(self):
        await self.fiscal.save(self.settings())
        old_total, old_stock, old_date = self.sale.total_amount, self.balance.quantity, self.sale.created_at
        first = await self.fiscal.prepare(self.sale.id)
        second = await self.fiscal.prepare(self.sale.id)
        self.assertEqual(first['id'], second['id']); self.assertFalse(first['submitted'])
        source = first['snapshot']['sale']
        self.assertEqual(source['created_at'], old_date.isoformat())
        self.assertEqual(source['total_amount'], str(old_total))
        self.assertEqual(source['employee_id'], str(self.employee.id))
        self.assertIsNone(source['client_created_at'])
        self.assertEqual(self.sale.total_amount, old_total); self.assertEqual(self.balance.quantity, old_stock)
        self.assertEqual(len(await self.fiscal.preparations()), 1)
        self.assertEqual(len(await self.fiscal.audits()), 2)
        altered = copy.deepcopy(first['snapshot']); altered['sale']['total_amount'] = '999'
        self.assertNotEqual(digest(altered), first['sha256'])

    async def test_refund_review_keeps_original_link_no_fabricated_fiscal_reference(self):
        await self.fiscal.save(self.settings())
        refund = Sale(company_id=self.company.id, branch_id=self.branch.id, device_id=self.device.id,
                      original_sale_id=self.sale.id, receipt_number=str(uuid4()), status='refunded', total_amount=-12, payment_method='cash')
        self.db.add(refund); await self.db.commit()
        result = await self.fiscal.prepare(refund.id)
        self.assertEqual(result['snapshot']['sale']['original_sale_id'], str(self.sale.id))
        self.assertNotIn('receiptID', result['snapshot']); self.assertFalse(result['submitted'])

    async def test_snapshots_and_audits_immutable_in_postgresql(self):
        await self.fiscal.save(self.settings()); await self.fiscal.prepare(self.sale.id)
        for table in ('fiscal_preparations', 'fiscal_audit'):
            for statement in (f'UPDATE {table} SET company_id=company_id WHERE company_id=:company', f'DELETE FROM {table} WHERE company_id=:company'):
                with self.assertRaises(DBAPIError):
                    async with self.db.begin_nested():
                        await self.db.execute(text(statement), {'company': self.company.id})

    async def test_snapshot_integrity_detects_unexpected_tampering(self):
        await self.fiscal.save(self.settings()); await self.fiscal.prepare(self.sale.id)
        row = (await self.db.execute(select(FiscalPreparation).where(FiscalPreparation.company_id == self.company.id))).scalar_one()
        row.snapshot_hash = '0' * 64
        with self.assertRaises(HTTPException): self.fiscal.preparation_view(row)
        await self.db.rollback()

    async def test_runtime_role_has_no_mutation_rights_on_fiscal_evidence(self):
        for table in ('fiscal_preparations', 'fiscal_audit'):
            for privilege in ('SELECT', 'INSERT', 'UPDATE', 'DELETE'):
                result = (await self.db.execute(text('SELECT has_table_privilege(:role,:table,:privilege)'),
                                                {'role': 'apex_user', 'table': table, 'privilege': privilege})).scalar_one()
                self.assertEqual(result, privilege in ('SELECT', 'INSERT'))

    async def test_populated_downgrade_refuses_data_loss(self):
        from migrations.versions import p9a_fiscal_preparation as migration
        await self.fiscal.save(self.settings())
        def guard(connection):
            with patch.object(migration.op, 'get_bind', return_value=connection):
                migration.downgrade()
        with self.assertRaisesRegex(RuntimeError, 'Fiscal data exists'):
            connection = await self.db.connection()
            await connection.run_sync(guard)
        self.assertEqual((await self.fiscal.configuration())['version'], 1)

    async def test_authenticated_api_owner_and_cross_tenant_rejection(self):
        async def override(): yield self.db
        app.dependency_overrides[get_db] = override
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://isolated.test') as client:
                path = f'/api/fiscal/{self.company.id}/configuration'
                self.assertEqual((await client.get(path)).status_code, 401)
                headers = {'Authorization': 'Bearer ' + create_access_token(str(self.user.id), self.user.email)}
                self.assertEqual((await client.get(path, headers=headers)).status_code, 200)
                self.assertEqual((await client.get(f'/api/fiscal/{uuid4()}/configuration', headers=headers)).status_code, 403)
                response = await client.put(path, headers=headers, json=self.settings().model_dump(mode='json'))
                self.assertEqual(response.status_code, 200, response.text)
                response = await client.post(f'/api/fiscal/{self.company.id}/preparations/{self.sale.id}', headers=headers)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertFalse(response.json()['submitted'])
        finally:
            app.dependency_overrides.pop(get_db, None)
