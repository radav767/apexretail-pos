"""Official v7.2 hash/QR vectors + explicitly SYNTHETIC local protocol fixtures.

No official private keys, FDMS credentials or network calls are used.
Synthetic acknowledgements are signed by ephemeral test-only keys, not ZIMRA.
"""
import base64
import copy
import json
from datetime import timedelta
from decimal import Decimal
from uuid import UUID, uuid4
import unittest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes
from cryptography.exceptions import InvalidSignature
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from app.models.fiscal_protocol import FiscalProtocolState, FiscalDocument
from app.models import Sale, SaleItem, Company
from app.fiscal.protocol import TestFiscalProtocol
from app.fiscal.communication import DeviceIdentity, TestDeviceChannel, FDMSOperationError
from app.fiscal.adapter import FiscalIntegrationUnavailable
from app.fiscal.service import FiscalService
from app.fiscal.signatures import receipt_message, day_message, sign_message, sha256, receipt_server_message, counter_message
from app.fiscal.receipt import validate_receipt
from app.fiscal.counters import fiscal_counters
from app.fiscal.offline import closed_day_file, wire_json
from app.fiscal.formatting import verification_url, receipt_preview
from app.fiscal.schema import FiscalSettings
import test_phase7d_operations as fixtures

THUMB = base64.b64encode(b'T' * 20).decode()


class EphemeralTestSigner:
    def __init__(self): self.key = ec.generate_private_key(ec.SECP256R1())
    def sign(self, message): return self.key.sign(message, ec.ECDSA(hashes.SHA256()))
    def verify(self, message, signature):
        try:
            self.key.public_key().verify(signature, message, ec.ECDSA(hashes.SHA256())); return True
        except InvalidSignature:
            return False


def synthetic_receipt(**changes):
    value = {'receiptType': 'FiscalInvoice', 'receiptCurrency': 'USD', 'receiptCounter': 1, 'receiptGlobalNo': 1,
        'invoiceNo': 'SYNTHETIC-1', 'receiptDate': '2026-10-21T09:00:00', 'receiptLinesTaxInclusive': True,
        'receiptLines': [{'receiptLineType': 'Sale', 'receiptLineNo': 1, 'receiptLineName': 'Synthetic product',
                         'receiptLinePrice': '12.00', 'receiptLineQuantity': '1', 'receiptLineTotal': '12.00', 'taxID': 1}],
        'receiptTaxes': [{'taxID': 1, 'taxAmount': '0.00', 'salesAmountWithTax': '12.00'}],
        'receiptPayments': [{'moneyTypeCode': 'Cash', 'paymentAmount': '12.00'}], 'receiptTotal': '12.00'}
    value.update(changes); return value


def synthetic_config():
    return {'taxPayerName': 'SYNTHETIC BUSINESS', 'taxPayerTIN': '0000000001', 'deviceSerialNo': 'SYNTHETIC',
        'deviceOperatingMode': 'Online', 'taxPayerDayMaxHrs': 24, 'taxpayerDayEndNotificationHrs': 2,
        'certificateValidTill': '2099-01-01', 'deviceBranchName': 'Synthetic branch',
        'deviceBranchAddress': {'street': 'Synthetic street', 'city': 'Test'}, 'deviceBranchContacts': {'email': 'test@example.test'},
        'applicableTaxes': [{'taxID': 1, 'taxValidFrom': '2020-01-01', 'taxName': 'Synthetic exempt'}]}


class OfficialVectorTests(unittest.TestCase):
    def test_official_credit_note_example_two_hash(self):
        # FDMS v7.2 p74 (PDF page index73), §13.2.1, CreditNote example2.
        receipt = {'receiptType': 'CreditNote', 'receiptCurrency': 'USD', 'receiptGlobalNo': 85, 'receiptCounter': 2,
            'receiptDate': '2020-09-19T09:23:07', 'receiptTotal': '-40.35', 'receiptTaxes': [
                {'taxID': 3, 'taxPercent': '14.5', 'taxAmount': '-3', 'salesAmountWithTax': '-23'},
                {'taxID': 1, 'taxAmount': '0', 'salesAmountWithTax': '-7'},
                {'taxID': 2, 'taxPercent': '0', 'taxAmount': '0', 'salesAmountWithTax': '-10'}]}
        message = receipt_message(322, receipt, 'hNVJXP/ACOiE8McD3pKsDlqBXpuaUqQOfPnMyfZWI9k=')
        self.assertEqual(sha256(message), 'F9/QB0vhxQlEF2nk+oebwP8V+qBcNlOFvoTeE/1QxPc=')

    def test_official_qr_url_assembly_examples(self):
        values = [(321, '2023-04-03T10:00:00', 1112223331, '4C8BE27663330417', '00000003210304202311122233314C8BE27663330417'),
                  (322, '2023-04-04T10:00:00', 1332, 'C10B0476B3B14678', '0000000322040420230000001332C10B0476B3B14678')]
        for device, date, global_no, data, expected in values:
            with self.subTest(device=device):
                self.assertEqual(verification_url('https://invoice.zimra.co.zw', device, date, global_no, data), 'https://invoice.zimra.co.zw/' + expected)

    def test_documented_invoice_example_one_inconsistency_is_not_hidden(self):
        # Published concatenation and printed hash do not agree. Preserve as a
        # clarification gate; never modify implementation to force this vector.
        text = '321FISCALINVOICEZWL4322019-09-19T15:43:12945000A0250000B0.000350000C15.0015000115000D15.0030000230000hNVJXP/ACOiE8McD3pKsDlqBXpuaUqQOfPnMyfZWI9k='
        self.assertEqual(sha256(text.encode()), 'eHAAOVqxrRVRliVOsik4sONXJ10nckqCWIhPyoMyguM=')
        self.assertNotEqual(sha256(text.encode()), 'zDxEalWUpwX2BcsYxRUAEfY/13OaCrTwDt01So3a6uU=')

    def test_chain_cents_exempt_zero_and_local_time_are_strict(self):
        receipt = synthetic_receipt()
        self.assertIn(b'1200', receipt_message(1, receipt, None))
        changed = copy.deepcopy(receipt); changed['receiptTaxes'][0]['taxPercent'] = '0'
        self.assertNotEqual(receipt_message(1, receipt, None), receipt_message(1, changed, None))
        for change, previous in [({'receiptCounter': 2}, None), ({}, 'invalid'), ({'receiptDate': '2026-10-21T09:00:00Z'}, None), ({'receiptTotal': '1.001'}, None)]:
            with self.subTest(change=change), self.assertRaises(ValueError): receipt_message(1, {**receipt, **change}, previous)


class FiscalLocalTests(unittest.TestCase):
    def test_signing_interface_verifies_and_never_exposes_keys(self):
        signer = EphemeralTestSigner(); result = sign_message(b'local-test', signer)
        self.assertEqual(result['hash'], sha256(b'local-test')); self.assertEqual(set(result), {'hash', 'signature'})
        class Invalid:
            def sign(self, message): return b'bad'
            def verify(self, message, signature): return False
        with self.assertRaises(ValueError): sign_message(b'local-test', Invalid())

    def test_receipt_validation_rejects_tax_identity_hs_and_line_mismatch(self):
        receipt = synthetic_receipt(); config = synthetic_config()
        validate_receipt(receipt, config, '2026-10-21T08:00:00', allowed_currencies={'USD'})
        for mutate in [lambda r: r['receiptLines'][0].update(taxID=99), lambda r: r['receiptLines'][0].update(receiptLinePrice='11'),
                       lambda r: r.update(receiptCurrency='XXX'), lambda r: r.update(receiptDate='2026-10-23T09:00:00')]:
            invalid = copy.deepcopy(receipt); mutate(invalid)
            with self.assertRaises(ValueError): validate_receipt(invalid, config, '2026-10-21T08:00:00', allowed_currencies={'USD'})
        config['vatNumber'] = '000000001'
        with self.assertRaises(ValueError): validate_receipt(receipt, config, '2026-10-21T08:00:00', allowed_currencies={'USD'})

    def test_counters_preserve_currency_and_credit_sign(self):
        first = synthetic_receipt()
        credit = synthetic_receipt(receiptType='CreditNote', receiptCurrency='EUR', receiptTotal='-12')
        credit['receiptTaxes'][0].update(taxAmount='0', salesAmountWithTax='-12')
        credit['receiptPayments'][0].update(paymentAmount='-12')
        rows = fiscal_counters([first, credit])
        self.assertTrue(any(r['fiscalCounterType'] == 'CreditNoteByTax' and r['fiscalCounterCurrency'] == 'EUR' and r['fiscalCounterValue'] == '-12.00' for r in rows))
        self.assertTrue(any(r['fiscalCounterType'] == 'SaleByTax' and r['fiscalCounterCurrency'] == 'USD' and r['fiscalCounterValue'] == '12.00' for r in rows))
        self.assertEqual(counter_message(rows), counter_message(list(reversed(rows))))

    def test_offline_export_exact_numbers_signatures_size_and_no_queue_mutation(self):
        signer = EphemeralTestSigner(); receipt = synthetic_receipt()
        receipt['receiptDeviceSignature'] = sign_message(receipt_message(1, receipt, None), signer)
        original = copy.deepcopy(receipt)
        counters = fiscal_counters([receipt])
        footer = {'fiscalDayCounters': counters, 'receiptCounter': 1, 'fiscalDayClosed': '2026-10-21T10:00:00',
                  'fiscalDayDeviceSignature': sign_message(day_message(1, 1, '2026-10-21T08:00:00', counters), signer)}
        args = dict(mode='Offline', device_id=1, day_no=1, opened='2026-10-21T08:00:00', closed='2026-10-21T10:00:00',
                    receipts=[receipt], footer=footer, sequence=1, status='FiscalDayClosed', device_verifier=signer.verify)
        result = closed_day_file(**args)
        decoded = json.loads(base64.b64decode(result['file']), parse_float=Decimal)
        self.assertEqual(decoded['content']['receipts'][0]['receiptTotal'], Decimal('12.00'))
        self.assertFalse(result['submitted']); self.assertEqual(receipt, original)
        with self.assertRaises(ValueError): closed_day_file(**{**args, 'mode': 'Online'})
        with self.assertRaises(ValueError): closed_day_file(**{**args, 'status': 'FiscalDayOpened'})
        invalid = copy.deepcopy(receipt); invalid['receiptTotal'] = '11'
        with self.assertRaises(ValueError): closed_day_file(**{**args, 'receipts': [invalid]})
        self.assertIn('123456789012345678.99', wire_json({'receiptTotal': '123456789012345678.99'}))

    def test_receipt_preview_escapes_content_watermark_and_paper_rules(self):
        receipt = synthetic_receipt(); receipt['receiptLines'][0]['receiptLineName'] = '<script>BAD</script>'
        for paper in ('58mm', '80mm', 'A4'):
            html = receipt_preview(receipt, synthetic_config(), device_id=1, day_no=1, paper=paper)
            self.assertNotIn('<script>', html); self.assertIn('NOT A VALID FISCAL DOCUMENT', html)
            self.assertIn('Number of items', html)
            # Generated synthetic render evidence; not application source or a print.
            from pathlib import Path
            from tempfile import TemporaryDirectory
            with TemporaryDirectory(prefix='phase9b-preview-') as folder:
                Path(folder,f'{paper}.html').write_text(html)
        receipt['receiptLinesTaxInclusive'] = False
        with self.assertRaises(ValueError): receipt_preview(receipt, synthetic_config(), device_id=1, day_no=1, paper='58mm')


class SyntheticTransport:
    def __init__(self, server_signer):
        self.server_signer = server_signer; self.calls = []; self.fail_submit_once = False; self.fail_open_once = False
        self.acks = {}; self.day = 0; self.status = 'FiscalDayClosed'; self.close_payload = None
        self.opened = None
    async def request(self, operation, identity, payload, headers, timeout):
        self.calls.append((operation, copy.deepcopy(payload), headers, timeout))
        if operation == 'getConfig': return {**synthetic_config(), 'operationID': 'SYNTHETIC-' + uuid4().hex}
        if operation == 'getStatus':
            response = {'fiscalDayStatus': self.status, 'lastFiscalDayNo': self.day, 'lastReceiptGlobalNo': max(self.acks, default=0)}
            if self.status == 'FiscalDayClosed' and self.day:
                closed = max([self.opened, *(ack['serverDate'] for ack in self.acks.values())])
                response.update(fiscalDayReconciliationMode='Auto', fiscalDayClosed=closed)
                message = (str(identity.device_id) + str(self.day) + self.opened[:10] + closed + 'AUTO' + counter_message(self.close_payload['fiscalDayCounters'])).encode()
                response['fiscalDayServerSignature'] = {**sign_message(message, self.server_signer), 'certificateThumbprint': THUMB}
            return response
        if operation == 'openDay':
            self.day = payload['fiscalDayNo']; self.status = 'FiscalDayOpened'; self.opened = payload['fiscalDayOpened']
            if self.fail_open_once: self.fail_open_once = False; raise TimeoutError('synthetic uncertain opening')
            return {'fiscalDayNo': self.day}
        if operation == 'closeDay':
            self.close_payload = payload; self.status = 'FiscalDayCloseInitiated'; return {'operationID': 'SYNTHETIC-CLOSE'}
        if operation == 'submitReceipt':
            receipt = payload['receipt']; number = receipt['receiptGlobalNo']
            if number not in self.acks:
                response = {'receiptID': 1000 + number, 'serverDate': receipt['receiptDate']}
                response['receiptServerSignature'] = {**sign_message(receipt_server_message(receipt, response), self.server_signer), 'certificateThumbprint': THUMB}
                self.acks[number] = response
            if self.fail_submit_once: self.fail_submit_once = False; raise TimeoutError('synthetic lost response after acceptance')
            return copy.deepcopy(self.acks[number])
        raise ValueError('Unsupported synthetic operation')


class FiscalProtocolTests(unittest.IsolatedAsyncioTestCase):
    cleanup = fixtures.Phase7DOperationsTests.cleanup
    async def asyncSetUp(self):
        await fixtures.Phase7DOperationsTests.asyncSetUp(self)
        self.fiscal = FiscalService(self.db, self.owner, self.company.id)
        # New synthetic transaction with complete snapshots; never alter a fixture's
        # existing immutable sale or disable its financial protection triggers.
        self.sale = Sale(company_id=self.company.id, shop_id=self.shop.id, branch_id=self.branch.id,
            device_id=self.device.id, employee_id=self.employee.id, receipt_number='T-' + uuid4().hex,
            base_currency_code='USD', total_amount=12, subtotal_amount=12, tax_amount=0, tax_rate=0,
            tax_inclusive=True, payment_method='cash')
        self.db.add(self.sale); await self.db.flush()
        self.item = SaleItem(sale_id=self.sale.id, product_id=self.product.id, product_name=self.product.name,
                             quantity=1, unit_price=12, line_total=12)
        self.db.add(self.item)
        await self.db.commit()
        self.settings = FiscalSettings(taxpayer_tin='0000000001', branch_id=self.branch.id, register_id=self.device.id,
            device_id=1, device_serial='SYNTHETIC', model_name='SYNTHETIC', model_version='test')
        await self.fiscal.save(self.settings)
        self.signer, self.server = EphemeralTestSigner(), EphemeralTestSigner()
        self.transport = SyntheticTransport(self.server)
        self.channel = TestDeviceChannel(DeviceIdentity(str(self.company.id), 1, 'SYNTHETIC', 'test', 'test'), self.transport)
        self.protocol = self.new_protocol()
        self.sale_id = self.sale.id; self.company_id = self.company.id
        self.date = self.sale.created_at.astimezone(__import__('zoneinfo').ZoneInfo('Africa/Harare')).replace(microsecond=0)
        self.opened = (self.date - timedelta(minutes=1)).strftime('%Y-%m-%dT%H:%M:%S')

    def new_protocol(self):
        return TestFiscalProtocol(self.db, self.owner, self.company.id, self.channel, self.signer,
                                 lambda message, signature, thumb: thumb == THUMB and self.server.verify(message, signature), {'USD'})

    async def ready(self):
        await self.protocol.initialise(); await self.protocol.open_day(self.opened)

    async def staged(self):
        prepared = await self.fiscal.prepare(self.sale_id)
        receipt = synthetic_receipt(invoiceNo=self.sale.receipt_number, receiptDate=self.date.strftime('%Y-%m-%dT%H:%M:%S'),
                                    receiptLinesTaxInclusive=self.sale.tax_inclusive)
        receipt['receiptLines'][0]['receiptLineName'] = self.item.product_name
        return await self.protocol.stage(prepared['id'], receipt), receipt

    async def test_persistent_open_issue_ack_and_async_close(self):
        await self.ready(); row, receipt = await self.staged()
        self.assertEqual(row.id, (await self.protocol.stage(row.preparation_id, receipt)).id)
        with self.assertRaises(HTTPException): await self.protocol.dispatch(row.id)
        await self.protocol.confirm_printed(row.id)
        ack = await self.protocol.dispatch(row.id)
        self.assertEqual(ack['receiptID'], 1001)
        runtime = await self.fiscal.runtime_status()
        self.assertEqual(runtime['documents'][0]['status'], 'acknowledged_test_validation_unknown')
        self.assertFalse(runtime['submission_enabled'])
        await self.protocol.close_day()
        self.assertEqual((await self.fiscal.runtime_status())['day_status'], 'FiscalDayCloseInitiated')
        with self.assertRaises(HTTPException): await self.protocol.open_day(self.opened)
        self.transport.status = 'FiscalDayClosed'
        await self.protocol.reconcile()
        self.assertEqual((await self.fiscal.runtime_status())['day_status'], 'FiscalDayClosed')
        self.assertEqual(self.balance.quantity, 100); self.assertEqual(self.sale.total_amount, 12)
        self.assertTrue(all(call[2] == {'DeviceModelName': 'SYNTHETIC', 'DeviceModelVersionNo': 'test'} and call[3] == 30.0 for call in self.transport.calls))

    async def test_uncertain_submission_restarts_and_retries_exact_original(self):
        await self.ready(); row, _ = await self.staged(); identifier = row.id
        await self.protocol.confirm_printed(identifier); self.transport.fail_submit_once = True
        with self.assertRaises(TimeoutError): await self.protocol.dispatch(identifier)
        from app.fiscal.router import sale_fiscal_status
        result = await sale_fiscal_status(self.company_id, self.sale_id, self.owner, self.db)
        self.assertIsNone(result['submitted']); self.assertEqual(result['status'], 'test_submission_requires_review')
        # A new protocol object uses DB state, not an in-memory receipt queue.
        await self.db.refresh(self.user); await self.db.refresh(self.company)
        resumed = self.new_protocol()
        ack = await resumed.dispatch(identifier)
        attempts = [call[1] for call in self.transport.calls if call[0] == 'submitReceipt']
        self.assertEqual(attempts[0], attempts[1]); self.assertEqual(len(self.transport.acks), 1)
        self.assertEqual(ack['receiptID'], 1001)
        count = len(attempts); await resumed.dispatch(identifier)
        self.assertEqual(count, len([call for call in self.transport.calls if call[0] == 'submitReceipt']))

    async def test_uncertain_open_reconciles_without_invented_day_number(self):
        await self.protocol.initialise(); self.transport.fail_open_once = True
        with self.assertRaises(TimeoutError): await self.protocol.open_day(self.opened)
        await self.protocol.reconcile()
        runtime = await self.fiscal.runtime_status()
        self.assertEqual(runtime['day_no'], 1); self.assertEqual(runtime['day_status'], 'FiscalDayOpened')

    async def test_documented_deferred_open_and_offline_receipts_recover_in_order(self):
        await self.protocol.initialise()
        count = len(self.transport.calls)
        await self.protocol.queue_open_day(self.opened)
        row, _ = await self.staged(); identifier = row.id
        await self.protocol.confirm_printed(identifier)
        self.assertEqual(len(self.transport.calls), count)
        with self.assertRaises(HTTPException): await self.protocol.dispatch(identifier)
        resumed = self.new_protocol()
        await resumed.resume_deferred_day(); await resumed.dispatch(identifier)
        self.assertEqual(len(self.transport.acks), 1)
        self.assertEqual([call[0] for call in self.transport.calls[-3:]], ['getStatus', 'openDay', 'submitReceipt'])

    async def test_populated_protocol_downgrade_is_refused(self):
        from unittest.mock import patch
        from migrations.versions import p9b_fiscal_protocol as migration
        await self.protocol.initialise()
        def downgrade(connection):
            with patch.object(migration.op, 'get_bind', return_value=connection): migration.downgrade()
        with self.assertRaisesRegex(RuntimeError, 'Fiscal protocol evidence exists'):
            await (await self.db.connection()).run_sync(downgrade)

    async def test_config_is_locked_after_protocol_initialisation(self):
        await self.protocol.initialise()
        with self.assertRaises(HTTPException): await self.fiscal.save(self.settings.model_copy(update={'expected_version': 1}))

    async def test_changed_timestamp_amount_or_retry_is_rejected(self):
        await self.ready(); row, receipt = await self.staged()
        changed = copy.deepcopy(receipt); changed['receiptTotal'] = '11'
        with self.assertRaises(HTTPException): await self.protocol.stage(row.preparation_id, changed)
        with self.assertRaises(HTTPException): await self.protocol.stage(uuid4(), receipt)

    async def test_payment_method_cannot_be_silently_changed(self):
        await self.ready(); prepared = await self.fiscal.prepare(self.sale_id)
        receipt = synthetic_receipt(invoiceNo=self.sale.receipt_number, receiptDate=self.date.strftime('%Y-%m-%dT%H:%M:%S'))
        receipt['receiptLines'][0]['receiptLineName'] = self.item.product_name
        receipt['receiptPayments'][0]['moneyTypeCode'] = 'Card'
        with self.assertRaisesRegex(ValueError, 'payment method differs'):
            await self.protocol.stage(prepared['id'], receipt)
        receipt['receiptPayments'][0]['moneyTypeCode'] = 'Cash'
        receipt['receiptDate'] = (self.date - timedelta(seconds=1)).strftime('%Y-%m-%dT%H:%M:%S')
        with self.assertRaisesRegex(ValueError, 'timestamp differs'):
            await self.protocol.stage(prepared['id'], receipt)

    async def test_production_channel_and_other_tenant_cannot_be_used(self):
        with self.assertRaises(FiscalIntegrationUnavailable): TestDeviceChannel(DeviceIdentity(str(self.company_id), 1, 'SYNTHETIC', 'test', 'production'), self.transport)
        other = TestDeviceChannel(DeviceIdentity(str(uuid4()), 1, 'SYNTHETIC', 'test', 'test'), self.transport)
        with self.assertRaises(FiscalIntegrationUnavailable): TestFiscalProtocol(self.db, self.owner, self.company_id, other, self.signer, None, {'USD'})
        with self.assertRaises(ValueError): await self.channel.call('inventedOperation')
        other_company = Company(name='Synthetic second company', owner_email=f'{uuid4()}@example.test')
        self.db.add(other_company); await self.db.flush()
        self.db.add(FiscalProtocolState(company_id=other_company.id, data={'device_id': 1})); await self.db.commit()
        with self.assertRaisesRegex(FiscalIntegrationUnavailable, 'already belongs'):
            await self.protocol.initialise()
        self.assertEqual(self.transport.calls, [])

    async def test_protocol_records_are_append_only(self):
        await self.ready(); await self.staged()
        for table in ('fiscal_documents', 'fiscal_protocol_events'):
            with self.assertRaises(DBAPIError):
                async with self.db.begin_nested():
                    await self.db.execute(text(f'DELETE FROM {table} WHERE company_id=:company'), {'company': self.company_id})

    async def test_untrusted_ack_remains_uncertain_and_does_not_confirm_receipt(self):
        await self.ready(); row, _ = await self.staged(); identifier = row.id
        await self.protocol.confirm_printed(identifier)
        self.protocol.server_verifier = lambda *args: False
        with self.assertRaises(ValueError): await self.protocol.dispatch(identifier)
        self.assertIsNone(await self.protocol.latest(identifier, 'receipt_acknowledged'))
        self.assertEqual((await self.fiscal.runtime_status())['pending_operation'], 'submitReceipt')

    async def test_remote_rejection_is_not_classified_as_success_or_transient_disconnect(self):
        await self.ready(); row, _ = await self.staged(); identifier = row.id
        await self.protocol.confirm_printed(identifier)
        original_call = self.transport.request
        async def reject(operation, *args):
            if operation == 'submitReceipt': raise FDMSOperationError(422, 'RCPT02')
            return await original_call(operation, *args)
        self.transport.request = reject
        with self.assertRaises(FDMSOperationError): await self.protocol.dispatch(identifier)
        with self.assertRaises(HTTPException): await self.protocol.dispatch(identifier)
        event = await self.protocol.latest(identifier, 'operation_rejected')
        self.assertEqual(event.details['status'], 422)

    async def test_later_receipt_cannot_overtake_unacknowledged_original(self):
        await self.ready(); first, template = await self.staged(); first_id = first.id
        second_sale = Sale(company_id=self.company_id, shop_id=self.shop.id, branch_id=self.branch.id,
            device_id=self.device.id, employee_id=self.employee.id, receipt_number='T-' + uuid4().hex,
            base_currency_code='USD', subtotal_amount=12, total_amount=12, tax_amount=0, tax_rate=0,
            tax_inclusive=True, payment_method='cash')
        self.db.add(second_sale); await self.db.flush()
        self.db.add(SaleItem(sale_id=second_sale.id, product_id=self.product.id, product_name=self.item.product_name,
                            quantity=1, unit_price=12, line_total=12)); await self.db.commit()
        source = await self.fiscal.prepare(second_sale.id)
        second = copy.deepcopy(template)
        second.update(receiptCounter=2, receiptGlobalNo=2, invoiceNo=second_sale.receipt_number,
                      receiptDate=second_sale.created_at.astimezone(__import__('zoneinfo').ZoneInfo('Africa/Harare')).strftime('%Y-%m-%dT%H:%M:%S'))
        row = await self.protocol.stage(source['id'], second); second_id = row.id
        await self.protocol.confirm_printed(second_id)
        with self.assertRaises(HTTPException): await self.protocol.dispatch(second_id)
        await self.protocol.confirm_printed(first_id); await self.protocol.dispatch(first_id)
        await self.protocol.dispatch(second_id)
        self.assertEqual(len(self.transport.acks), 2)

    async def test_read_api_preview_and_employee_branch_permissions(self):
        import httpx
        from dataclasses import replace
        from types import SimpleNamespace
        from app.main import app
        from app.db.session import get_db
        from app.auth.dependencies import get_auth_actor
        await self.ready(); row, _ = await self.staged()
        async def override(): yield self.db
        app.dependency_overrides[get_db] = override
        app.dependency_overrides[get_auth_actor] = lambda: self.owner
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://isolated.test') as client:
                response = await client.get(f'/api/fiscal/{self.company_id}/documents/{row.id}/preview')
                self.assertEqual(response.status_code, 200); self.assertIn('NOT A VALID FISCAL DOCUMENT', response.text)
                self.assertEqual(response.headers['cache-control'], 'no-store')
                path = f'/api/fiscal/{self.company_id}/sales/{self.sale_id}/status'
                app.dependency_overrides[get_auth_actor] = lambda: self.waiter
                response = await client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()['status'], 'test_receipt_queued')
                app.dependency_overrides[get_auth_actor] = lambda: replace(self.waiter, permissions={})
                self.assertEqual((await client.get(path)).status_code, 403)
                app.dependency_overrides[get_auth_actor] = lambda: replace(self.waiter, employee=SimpleNamespace(id=self.employee.id, branch_id=uuid4()))
                self.assertEqual((await client.get(path)).status_code, 403)
        finally:
            app.dependency_overrides.pop(get_db, None); app.dependency_overrides.pop(get_auth_actor, None)
