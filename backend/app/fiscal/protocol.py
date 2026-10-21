"""Persistent test-device protocol. No public write routes or live transport.

Every remote mutation has a committed local intent. Ambiguous receipt retries
reuse the exact signed payload; a crashed in-flight day operation needs review.
"""
import copy
from datetime import datetime, timezone, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy import select, text
from app.models import Company, TipEntry
from app.models.fiscal import FiscalConfiguration, FiscalPreparation
from app.models.fiscal_protocol import FiscalProtocolState, FiscalDocument, FiscalProtocolEvent
from .service import FiscalService, digest
from .adapter import FiscalIntegrationUnavailable
from .communication import TestDeviceChannel, FDMSOperationError
from .receipt import validate_receipt
from .signatures import receipt_message, day_message, sign_message, verify_server_receipt, local_time, sha256, binary
from .counters import fiscal_counters
from .validation import number


class TestFiscalProtocol:
    __test__ = False

    def __init__(self, db, actor, company_id, channel: TestDeviceChannel, signer, trusted_server_verifier, allowed_currencies):
        self.service = FiscalService(db, actor, company_id)
        if channel.identity.environment != 'test' or channel.identity.company_id != str(company_id):
            raise FiscalIntegrationUnavailable('Channel must be bound to this business in test mode')
        self.db, self.company_id, self.channel = db, company_id, channel
        self.signer, self.server_verifier = signer, trusted_server_verifier
        self.allowed_currencies = frozenset(allowed_currencies)

    async def lock(self):
        await self.db.execute(select(Company.id).where(Company.id == self.company_id).with_for_update())
        settings = await self.db.get(FiscalConfiguration, self.company_id, populate_existing=True)
        if not settings or settings.settings['environment'] != 'test':
            raise FiscalIntegrationUnavailable('Only configured test devices are supported')
        identity = self.channel.identity
        if (settings.settings['device_id'], settings.settings['model_name'], settings.settings['model_version']) != (identity.device_id, identity.model_name, identity.model_version):
            raise FiscalIntegrationUnavailable('Device channel binding mismatch')
        state = await self.db.get(FiscalProtocolState, self.company_id, populate_existing=True)
        if state and state.data['configuration_hash'] != digest(settings.settings):
            raise FiscalIntegrationUnavailable('Fiscal settings changed; reviewed recommissioning required')
        if state:
            state.data = copy.deepcopy(state.data)
        return settings, state

    def event(self, state, kind, details, document_id=None):
        data = copy.deepcopy(state.data)
        data['sequence'] += 1
        state.data = data
        self.db.add(FiscalProtocolEvent(company_id=self.company_id, document_id=document_id,
                                       sequence=data['sequence'], kind=kind, details=details))
        self.service.audit('fiscal_test_' + kind, {'sequence': data['sequence'], 'document_id': str(document_id) if document_id else None})

    async def initialise(self):
        settings, state = await self.lock()
        if state:
            return copy.deepcopy(state.data)
        # A registered FDMS device has one numbering/hash namespace, even when
        # two tenant drafts mistakenly contain the same device ID. Serialise the
        # claim across companies, not only within a company's row lock.
        await self.db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': 9_000_000_000 + self.channel.identity.device_id})
        claimed = (await self.db.execute(select(FiscalProtocolState.company_id).where(
            FiscalProtocolState.company_id != self.company_id,
            FiscalProtocolState.data['device_id'].as_integer() == self.channel.identity.device_id).limit(1))).scalar_one_or_none()
        if claimed:
            raise FiscalIntegrationUnavailable('Fiscal test device already belongs to another business protocol')
        config = await self.channel.call('getConfig')
        config = {key: value for key, value in config.items() if key != 'operationID'}
        remote = await self.channel.call('getStatus') if config.get('deviceOperatingMode') == 'Online' else None
        if remote is None:
            raise FiscalIntegrationUnavailable('Offline-mode commissioning needs the approved file workflow')
        if config.get('taxPayerTIN') != settings.settings['taxpayer_tin'] or config.get('deviceSerialNo') != settings.settings['device_serial']:
            raise ValueError('FDMS taxpayer/device differs from business configuration')
        if remote.get('fiscalDayStatus') != 'FiscalDayClosed' or remote.get('lastFiscalDayNo', 0) or remote.get('lastReceiptGlobalNo', 0):
            raise FiscalIntegrationUnavailable('Existing device history requires reviewed state import; never invent counters')
        if not isinstance(config.get('taxPayerDayMaxHrs'), int) or config['taxPayerDayMaxHrs'] <= 0 or not isinstance(config.get('applicableTaxes'), list):
            raise ValueError('Incomplete FDMS configuration')
        if config.get('certificateValidTill', '') < datetime.now(timezone.utc).date().isoformat():
            raise ValueError('Fiscal device certificate expired or missing')
        state = FiscalProtocolState(company_id=self.company_id, data={'configuration_hash': digest(settings.settings),
            'device_id': self.channel.identity.device_id,
            'config': config, 'status': 'FiscalDayClosed', 'day_no': 0, 'last_global': 0, 'last_counter': 0,
            'last_hash': None, 'last_receipt': None, 'opened': None, 'pending': None, 'sequence': 0})
        self.db.add(state); self.event(state, 'initialised', {'remote_status': 'FiscalDayClosed'})
        await self.db.commit()
        return copy.deepcopy(state.data)

    async def begin(self, operation, payload, *, document=None, replace_deferred=False):
        _, state = await self.lock()
        if state is None:
            raise HTTPException(409, 'Fiscal operation pending or device uninitialised; reconcile first')
        pending = state.data['pending']
        if pending and not (replace_deferred and pending.get('deferred') and pending['operation'] == operation == 'openDay' and pending['payload'] == payload):
            raise HTTPException(409, 'Fiscal operation pending; reconcile first')
        token = str(uuid4())
        state.data['pending'] = {'token': token, 'operation': operation, 'payload': copy.deepcopy(payload),
                                 'document': str(document.id) if document else None}
        self.event(state, 'operation_started', {'operation': operation, 'token': token}, document.id if document else None)
        await self.db.commit()
        return token

    async def invoke(self, operation, payload, finish, *, document=None, replace_deferred=False):
        document_id = document.id if document else None
        token = await self.begin(operation, payload, document=document, replace_deferred=replace_deferred)
        try:
            response = await self.channel.call(operation, copy.deepcopy(payload))
            _, state = await self.lock()
            if not state.data['pending'] or state.data['pending']['token'] != token:
                raise HTTPException(409, 'Fiscal operation intent mismatch')
            await finish(state, response)
            state.data['pending'] = None
            self.event(state, 'operation_completed', {'operation': operation}, document_id)
            await self.db.commit()
            return response
        except Exception as error:
            # Retain exact request for review/retry. Never include raw exception text,
            # HTTP credentials or provider-echoed request bodies in audit records.
            await self.db.rollback()
            _, state = await self.lock()
            if state and (state.data.get('pending') or {}).get('token') == token:
                rejected = isinstance(error, FDMSOperationError) and error.status < 500
                pending = copy.deepcopy(state.data['pending']); pending['uncertain'] = not rejected
                if rejected:
                    pending['rejection'] = {'status': error.status, 'code': error.code}
                state.data['pending'] = pending
                self.event(state, 'operation_rejected' if rejected else 'operation_uncertain',
                           {'operation': operation, 'error_class': type(error).__name__, **(pending.get('rejection') or {})}, document_id)
                await self.db.commit()
            raise

    async def open_day(self, opened):
        _, state = await self.lock()
        if not state or state.data['status'] != 'FiscalDayClosed' or state.data['pending']:
            raise HTTPException(409, 'Previous fiscal day must be confirmed closed')
        local_time(opened)
        if local_time(opened) > datetime.now(ZoneInfo('Africa/Harare')).replace(tzinfo=None):
            raise ValueError('Fiscal day cannot be opened with an invented future timestamp')
        if state.data.get('closed') and local_time(opened) < local_time(state.data['closed']):
            raise ValueError('Fiscal day cannot precede previous verified closing')
        # Refresh config before opening. Existing snapshots are never rewritten.
        config = await self.channel.call('getConfig')
        config = {key: value for key, value in config.items() if key != 'operationID'}
        if config != state.data['config']:
            raise FiscalIntegrationUnavailable('FDMS configuration changed; reviewed refresh required')
        payload = {'fiscalDayOpened': opened, 'fiscalDayNo': state.data['day_no'] + 1}
        async def finish(current, response):
            if response.get('fiscalDayNo') != payload['fiscalDayNo']:
                raise ValueError('FDMS opened unexpected fiscal day')
            current.data.update(status='FiscalDayOpened', day_no=payload['fiscalDayNo'], opened=opened,
                                last_counter=0, last_hash=None, last_receipt=None)
        return await self.invoke('openDay', payload, finish)

    async def queue_open_day(self, opened):
        """§2.2/§9 delayed opening in Online mode with cached FDMS configuration.

        No first-time offline commissioning and no reassignment of old receipts.
        Receipts may be prepared locally but cannot be submitted before openDay.
        """
        _, state = await self.lock()
        if not state or state.data['status'] != 'FiscalDayClosed' or state.data['pending']:
            raise HTTPException(409, 'Previous fiscal day must be confirmed closed')
        now = datetime.now(ZoneInfo('Africa/Harare')).replace(tzinfo=None)
        if local_time(opened) > now or state.data['config']['certificateValidTill'] < now.date().isoformat():
            raise ValueError('Invalid opening timestamp or expired fiscal certificate')
        if state.data.get('closed') and local_time(opened) < local_time(state.data['closed']):
            raise ValueError('Deferred day cannot precede previous verified closing')
        payload = {'fiscalDayOpened': opened, 'fiscalDayNo': state.data['day_no'] + 1}
        state.data.update(status='LocalDayOpenedPending', day_no=payload['fiscalDayNo'], opened=opened,
                          last_counter=0, last_hash=None, last_receipt=None)
        state.data['pending'] = {'operation': 'openDay', 'payload': payload, 'token': str(uuid4()),
                                 'document': None, 'deferred': True, 'previous_global': state.data['last_global']}
        self.event(state, 'day_open_deferred', {'payload': payload})
        await self.db.commit()

    async def resume_deferred_day(self):
        _, state = await self.lock()
        pending = state.data.get('pending') if state else None
        if not pending or not pending.get('deferred') or pending['operation'] != 'openDay':
            raise HTTPException(409, 'No never-submitted deferred opening exists')
        remote = await self.channel.call('getStatus')
        if (remote.get('fiscalDayStatus') != 'FiscalDayClosed' or remote.get('lastFiscalDayNo', 0) != state.data['day_no'] - 1
            or remote.get('lastReceiptGlobalNo', 0) != pending['previous_global']):
            raise ValueError('Remote fiscal day changed; do not guess or reassign queued receipts')
        payload = copy.deepcopy(pending['payload'])
        async def finish(current, response):
            if response.get('fiscalDayNo') != current.data['day_no']:
                raise ValueError('FDMS opened unexpected deferred day')
            current.data['status'] = 'FiscalDayOpened'
        return await self.invoke('openDay', payload, finish, replace_deferred=True)

    async def stage(self, preparation_id, receipt, *, original_document_id=None):
        settings, state = await self.lock()
        previous = (await self.db.execute(select(FiscalDocument).where(FiscalDocument.company_id == self.company_id,
            FiscalDocument.preparation_id == preparation_id))).scalar_one_or_none()
        if previous:
            comparable = {k: v for k, v in previous.payload.items() if k != 'receiptDeviceSignature'}
            if comparable != receipt:
                raise HTTPException(409, 'Prepared receipt retry differs from immutable original')
            return previous
        deferred = (state is not None and state.data['status'] == 'LocalDayOpenedPending'
                    and (state.data.get('pending') or {}).get('operation') == 'openDay'
                    and not (state.data.get('pending') or {}).get('rejection'))
        if state is None or (not deferred and (state.data['status'] not in ('FiscalDayOpened', 'FiscalDayCloseFailed') or state.data['pending'])):
            raise HTTPException(409, 'Fiscal day is not ready for new receipts')
        current = datetime.now(ZoneInfo('Africa/Harare')).replace(tzinfo=None)
        if current > local_time(state.data['opened']) + timedelta(hours=state.data['config']['taxPayerDayMaxHrs']):
            raise ValueError('Fiscal day duration exceeded; source must not be backdated/reassigned')
        if state.data['config']['certificateValidTill'] < current.date().isoformat():
            raise FiscalIntegrationUnavailable('Fiscal certificate renewal required')
        source = (await self.db.execute(select(FiscalPreparation).where(FiscalPreparation.company_id == self.company_id,
            FiscalPreparation.id == preparation_id))).scalar_one_or_none()
        if source is None or digest(source.snapshot) != source.snapshot_hash:
            raise HTTPException(404, 'Source review missing or invalid')
        sale = source.snapshot['sale']
        if (source.snapshot['configuration_version'] != settings.version or source.snapshot['configuration_hash'] != digest(settings.settings)
            or sale['branch_id'] != settings.settings['branch_id'] or sale['device_id'] != settings.settings['register_id']):
            raise ValueError('Source review no longer matches fiscal device configuration')
        if number(receipt['receiptTotal']) != number(sale['total_amount']) or receipt['invoiceNo'] != sale['receipt_number']:
            raise ValueError('Receipt amount/identity differs from immutable source sale')
        if not sale.get('base_currency_code') or receipt['receiptCurrency'] != sale['base_currency_code']:
            raise ValueError('Missing or mismatched original sale currency')
        if sale.get('payment_currency_code') not in (None, sale['base_currency_code']):
            raise ValueError('Multi-currency tender mapping requires commissioning; no inferred conversion')
        method = sale.get('refund_method') or sale['payment_method']
        payment_code = {'cash': 'Cash', 'card': 'Card', 'mobile': 'MobileWallet', 'credit': 'Credit'}.get(method)
        if payment_code is None or len(receipt['receiptPayments']) != 1 or receipt['receiptPayments'][0]['moneyTypeCode'] != payment_code:
            raise ValueError('Fiscal payment method differs from immutable sale; split tender is not commissioned')
        if number(sale.get('discount_amount') or 0) != 0:
            raise ValueError('Discount mapping requires reviewed fiscal discount lines')
        tipped = (await self.db.execute(select(TipEntry.id).where(TipEntry.company_id == self.company_id,
            TipEntry.sale_id == source.sale_id).limit(1))).scalar_one_or_none()
        if tipped:
            raise ValueError('Tip fiscal treatment requires commissioning; no inferred product revenue')
        if receipt['receiptLinesTaxInclusive'] != sale['tax_inclusive'] or sum(number(t['taxAmount']) for t in receipt['receiptTaxes']) != number(sale['tax_amount']):
            raise ValueError('Fiscal tax totals differ from immutable sale')
        if len(receipt['receiptLines']) != len(source.snapshot['items']):
            raise ValueError('Automatic discount/extra-charge line mapping is not commissioned')
        for line, item in zip(receipt['receiptLines'], source.snapshot['items'], strict=True):
            if (line.get('receiptLineType') != 'Sale' or line.get('receiptLineName') != item['product_name']
                or number(line['receiptLineQuantity']) != abs(number(item['quantity']))
                or number(line['receiptLineTotal']) != number(item['line_total'])):
                raise ValueError('Fiscal line differs from immutable source item')
        original_stamp = sale.get('client_created_at') or sale['created_at']
        stamp = datetime.fromisoformat(original_stamp)
        if stamp.tzinfo is None:
            raise ValueError('Original transaction has no timezone; manual clarification required')
        # FDMS uses Zimbabwe local time, not browser timezone or a newly invented time.
        if receipt['receiptDate'] != stamp.astimezone(ZoneInfo('Africa/Harare')).strftime('%Y-%m-%dT%H:%M:%S'):
            raise ValueError('Receipt timestamp differs from original transaction')
        if receipt['receiptCounter'] != state.data['last_counter'] + 1 or receipt['receiptGlobalNo'] != state.data['last_global'] + 1:
            raise ValueError('Fiscal numbering is not sequential')
        if local_time(receipt['receiptDate']) > datetime.now(ZoneInfo('Africa/Harare')).replace(tzinfo=None):
            raise ValueError('Future receipt timestamp cannot be invented')
        original = None; original_id = None; credited = number('0')
        if receipt['receiptType'] != 'FiscalInvoice':
            original_row = await self.document(original_document_id)
            original_source = await self.db.get(FiscalPreparation, original_row.preparation_id)
            if sale.get('original_sale_id') != str(original_source.sale_id):
                raise ValueError('Refund does not reference original source sale')
            ack = await self.latest(original_row.id, 'receipt_acknowledged')
            if not ack:
                raise ValueError('Original fiscal acknowledgement required')
            original, original_id = original_row.payload, ack.details['receiptID']
            # Includes all issued/staged credits, not only acknowledged credits.
            rows = (await self.db.execute(select(FiscalDocument).where(FiscalDocument.company_id == self.company_id))).scalars().all()
            for row in rows:
                if row.payload.get('creditDebitNote', {}).get('receiptID') == original_id:
                    credited -= number(row.payload['receiptTotal'])
        elif sale.get('original_sale_id'):
            raise ValueError('Refund must use a credit/debit note, never a new invoice')
        validate_receipt(receipt, state.data['config'], state.data['opened'], allowed_currencies=self.allowed_currencies,
                         previous=state.data['last_receipt'], original=original, original_receipt_id=original_id, already_credited=credited)
        payload = copy.deepcopy(receipt)
        payload['receiptDeviceSignature'] = sign_message(receipt_message(self.channel.identity.device_id, payload, state.data['last_hash']), self.signer)
        row = FiscalDocument(company_id=self.company_id, preparation_id=preparation_id, day_no=state.data['day_no'],
                             global_no=receipt['receiptGlobalNo'], payload=payload, payload_hash=digest(payload))
        self.db.add(row); await self.db.flush()
        state.data.update(last_counter=receipt['receiptCounter'], last_global=receipt['receiptGlobalNo'],
                          last_hash=payload['receiptDeviceSignature']['hash'], last_receipt=payload)
        self.event(state, 'receipt_staged', {'payload_hash': row.payload_hash}, row.id)
        await self.db.commit()
        return row

    async def document(self, document_id):
        row = (await self.db.execute(select(FiscalDocument).where(FiscalDocument.company_id == self.company_id,
                                                                FiscalDocument.id == document_id))).scalar_one_or_none()
        if row is None or digest(row.payload) != row.payload_hash:
            raise HTTPException(404, 'Fiscal document missing or invalid')
        return row

    async def latest(self, document_id, kind):
        return (await self.db.execute(select(FiscalProtocolEvent).where(FiscalProtocolEvent.company_id == self.company_id,
            FiscalProtocolEvent.document_id == document_id, FiscalProtocolEvent.kind == kind)
            .order_by(FiscalProtocolEvent.sequence.desc()).limit(1))).scalar_one_or_none()

    async def confirm_printed(self, document_id):
        _, state = await self.lock(); row = await self.document(document_id)
        if not await self.latest(row.id, 'receipt_printed'):
            self.event(state, 'receipt_printed', {'caller_confirmed': True}, row.id); await self.db.commit()

    async def dispatch(self, document_id):
        _, state = await self.lock(); row = await self.document(document_id)
        ack = await self.latest(row.id, 'receipt_acknowledged')
        if ack:
            return copy.deepcopy(ack.details)
        if not state or state.data['status'] not in ('FiscalDayOpened', 'FiscalDayCloseFailed') or row.day_no != state.data['day_no']:
            raise HTTPException(409, 'Receipt belongs to a different or closed fiscal day; reviewed recovery required')
        if not await self.latest(row.id, 'receipt_printed'):
            raise HTTPException(409, 'Receipt must be printed before FDMS submission')
        earlier = (await self.db.execute(select(FiscalDocument).where(FiscalDocument.company_id == self.company_id,
            FiscalDocument.global_no < row.global_no).order_by(FiscalDocument.global_no))).scalars().all()
        for prior in earlier:
            if not await self.latest(prior.id, 'receipt_acknowledged'):
                raise HTTPException(409, 'Earlier receipt must be reconciled first')
        pending = state.data.get('pending')
        if pending:
            if pending.get('operation') != 'submitReceipt' or pending.get('document') != str(row.id) or not pending.get('uncertain'):
                raise HTTPException(409, 'Different/in-flight fiscal operation requires review')
            # Official §4.7 deduplicates identical device/global/hash resubmission.
            if pending['payload'] != {'receipt': row.payload}:
                raise HTTPException(409, 'Pending fiscal identity mismatch')
            state.data['pending'] = None
            self.event(state, 'identical_receipt_retry', {'payload_hash': row.payload_hash}, row.id)
            await self.db.commit()
        async def finish(current, response):
            verify_server_receipt(row.payload, response, self.server_verifier)
            details = {key: response[key] for key in ('receiptID', 'serverDate', 'receiptServerSignature')}
            details['validation_status'] = 'not_confirmed'
            self.event(current, 'receipt_acknowledged', details, row.id)
        return await self.invoke('submitReceipt', {'receipt': row.payload}, finish, document=row)

    async def close_day(self):
        _, state = await self.lock()
        if not state or state.data['status'] not in ('FiscalDayOpened', 'FiscalDayCloseFailed') or state.data['pending']:
            raise HTTPException(409, 'Fiscal day is not ready to close')
        rows = (await self.db.execute(select(FiscalDocument).where(FiscalDocument.company_id == self.company_id,
                                                                  FiscalDocument.day_no == state.data['day_no']))).scalars().all()
        for row in rows:
            if not await self.latest(row.id, 'receipt_acknowledged'):
                raise HTTPException(409, 'Unacknowledged fiscal receipts block day closure')
        counters = fiscal_counters([row.payload for row in rows])
        payload = {'fiscalDayNo': state.data['day_no'], 'receiptCounter': state.data['last_counter'], 'fiscalDayCounters': counters,
                   'fiscalDayDeviceSignature': sign_message(day_message(self.channel.identity.device_id, state.data['day_no'], state.data['opened'], counters), self.signer)}
        async def finish(current, response):
            if not isinstance(response.get('operationID'), str) or not response['operationID']:
                raise ValueError('Missing close operation acknowledgement')
            current.data['status'] = 'FiscalDayCloseInitiated'
            self.event(current, 'day_close_requested', {'payload': payload, 'operationID': response['operationID']})
        return await self.invoke('closeDay', payload, finish)

    async def reconcile(self):
        _, state = await self.lock()
        if not state:
            raise HTTPException(409, 'Fiscal device uninitialised')
        response = await self.channel.call('getStatus')
        remote_status = response.get('fiscalDayStatus')
        if remote_status not in ('FiscalDayOpened', 'FiscalDayClosed', 'FiscalDayCloseInitiated', 'FiscalDayCloseFailed'):
            raise ValueError('Unknown remote fiscal status')
        pending = state.data.get('pending')
        expected_day = pending['payload']['fiscalDayNo'] if pending and pending['operation'] == 'openDay' else state.data['day_no']
        if response.get('lastFiscalDayNo') != expected_day:
            raise ValueError('Remote fiscal day mismatch; reviewed recovery required')
        if response.get('lastReceiptGlobalNo', 0) > state.data['last_global']:
            raise ValueError('Remote device has receipts unknown to this business ledger')
        # Status never proves that a specific receipt hash was received/validated.
        if pending and pending['operation'] == 'submitReceipt':
            self.event(state, 'receipt_status_inconclusive', {'remote_status': remote_status})
            await self.db.commit(); return response
        if pending and (not pending.get('uncertain') or pending['operation'] not in ('openDay', 'closeDay')):
            raise HTTPException(409, 'In-flight operation requires explicit worker recovery review')
        if pending and pending['operation'] == 'closeDay' and remote_status == 'FiscalDayOpened':
            raise HTTPException(409, 'Closing outcome remains uncertain; do not issue more receipts')
        if state.data['status'] == 'FiscalDayClosed' and remote_status != 'FiscalDayClosed' and not (pending and pending['operation'] == 'openDay'):
            raise ValueError('Unexpected remote fiscal-day reopening')
        if remote_status == 'FiscalDayClosed':
            # Closing server signature verification uses §13.3.2; manual counters
            # need separate reviewed reconciliation, never silently overwrite ours.
            if response.get('fiscalDayReconciliationMode') != 'Auto':
                raise ValueError('Manual fiscal-day closure requires reviewed reconciliation')
            closed = local_time(response['fiscalDayClosed'])
            if (not state.data['opened'] or closed < local_time(state.data['opened'])
                or (state.data['last_receipt'] and closed < local_time(state.data['last_receipt']['receiptDate']))):
                raise ValueError('Invalid fiscal closing timestamp')
            rows = (await self.db.execute(select(FiscalDocument).where(FiscalDocument.company_id == self.company_id,
                                                                      FiscalDocument.day_no == state.data['day_no']))).scalars().all()
            counters = fiscal_counters([row.payload for row in rows])
            message = (str(self.channel.identity.device_id) + str(state.data['day_no']) + state.data['opened'][:10]
                       + response['fiscalDayClosed'] + 'AUTO').encode()
            from .signatures import counter_message
            message += counter_message(counters).encode()
            signature = response['fiscalDayServerSignature']; binary(signature['certificateThumbprint'], 20)
            if signature['hash'] != sha256(message) or not self.server_verifier(message, binary(signature['signature']), signature['certificateThumbprint']):
                raise ValueError('Untrusted fiscal-day closing signature')
            state.data['closed'] = response['fiscalDayClosed']
        if pending and pending['operation'] == 'openDay':
            if remote_status != 'FiscalDayOpened':
                raise ValueError('Ambiguous day opening; operator review required')
            if state.data['status'] != 'LocalDayOpenedPending':
                state.data.update(day_no=pending['payload']['fiscalDayNo'], opened=pending['payload']['fiscalDayOpened'],
                                  last_counter=0, last_hash=None, last_receipt=None)
        state.data['status'] = remote_status
        state.data['pending'] = None
        self.event(state, 'day_status_reconciled', {'response': response})
        await self.db.commit()
        return response
