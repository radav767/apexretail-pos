import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import select
from app.auth.dependencies import ensure_company_access, require_owner
from app.models import Branch, Company, Device, Sale, SaleItem
from app.models.fiscal import FiscalAudit, FiscalConfiguration, FiscalPreparation
from app.models.fiscal_protocol import FiscalProtocolState, FiscalDocument, FiscalProtocolEvent
from .schema import FiscalSettings


def digest(snapshot: dict) -> str:
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


class FiscalService:
    def __init__(self, db, actor, company_id: UUID):
        ensure_company_access(actor, company_id)
        require_owner(actor)
        # Fiscal secrets and tax setup are owner-account operations, not POS PIN operations.
        if actor.actor_type != 'user' or actor.user is None or actor.role != 'owner':
            raise HTTPException(403, 'Business owner account required')
        self.db, self.actor, self.company_id = db, actor, company_id
        self.actor_user_id = actor.user.id

    def audit(self, action, details):
        self.db.add(FiscalAudit(company_id=self.company_id, actor_user_id=self.actor_user_id, action=action, details=details))

    async def configuration(self):
        config = await self.db.get(FiscalConfiguration, self.company_id)
        settings = dict(config.settings) if config else None
        if settings is not None:
            settings['credential_configured'] = bool(settings.pop('credential_reference', None))
        return {'version': config.version if config else 0, 'settings': settings,
                'submission_enabled': False, 'certification': 'not_approved',
                'remote_status': 'not_checked', 'operating_mode': 'uncommissioned',
                'blockers': ['ZIMRA test onboarding and current OpenAPI confirmation',
                             'Device certificate provisioning and verified signing',
                             'Fiscal day, receipt and offline conformance tests',
                             'ZIMRA approval and separate live activation authorization']}

    async def save(self, data: FiscalSettings):
        # Lock the parent as well: serialises first configuration and snapshot requests.
        await self.db.execute(select(Company.id).where(Company.id == self.company_id).with_for_update())
        config = await self.db.get(FiscalConfiguration, self.company_id, populate_existing=True)
        if data.expected_version != (config.version if config else 0):
            raise HTTPException(409, 'Fiscal settings changed; reload before saving')
        if await self.db.get(FiscalProtocolState, self.company_id):
            raise HTTPException(409, 'Fiscal protocol is initialised; reviewed recommissioning required before configuration changes')
        branch = await self.db.get(Branch, data.branch_id)
        device = await self.db.get(Device, data.register_id)
        if not branch or branch.company_id != self.company_id or not device or device.company_id != self.company_id or device.branch_id != branch.id:
            raise HTTPException(403, 'Fiscal register and branch must belong to this business')
        reference = (config.settings.get('credential_reference') if config and 'credential_reference' not in data.model_fields_set
                     else data.credential_reference)
        if reference and not reference.startswith(f'fiscal/{self.company_id}/'):
            raise HTTPException(422, 'Credential reference must be scoped to this business')
        settings = data.model_dump(mode='json', exclude={'expected_version'})
        settings['credential_reference'] = reference
        # Store drafts only: no validation claim about taxpayer identity or FDMS tax IDs.
        if config is None:
            config = FiscalConfiguration(company_id=self.company_id, version=1, settings=settings)
            self.db.add(config)
        else:
            config.version += 1
            config.settings = settings
        config.updated_at = datetime.now(timezone.utc)
        self.audit('fiscal_configuration_saved', {'version': config.version, 'settings_hash': digest(settings),
                                                'settings': {key: value for key, value in settings.items() if key != 'credential_reference'},
                                                'credential_configured': bool(reference), 'submission_enabled': False})
        await self.db.commit()
        return await self.configuration()

    async def prepare(self, sale_id: UUID):
        await self.db.execute(select(Company.id).where(Company.id == self.company_id).with_for_update())
        sale = (await self.db.execute(select(Sale).where(Sale.id == sale_id, Sale.company_id == self.company_id))).scalar_one_or_none()
        if sale is None:
            raise HTTPException(404, 'Sale not found')
        previous = (await self.db.execute(select(FiscalPreparation).where(
            FiscalPreparation.company_id == self.company_id, FiscalPreparation.sale_id == sale_id))).scalar_one_or_none()
        if previous:
            return self.preparation_view(previous)
        config = await self.db.get(FiscalConfiguration, self.company_id)
        if config is None:
            raise HTTPException(409, 'Save fiscal configuration before preparing a review snapshot')
        if str(sale.branch_id) != config.settings['branch_id'] or str(sale.device_id) != config.settings['register_id']:
            raise HTTPException(409, 'Sale register does not match fiscal configuration')
        items = (await self.db.execute(select(SaleItem).where(SaleItem.sale_id == sale.id).order_by(SaleItem.id))).scalars().all()
        # Exact source-column values, never invented receipt counters, dates, rates or signs.
        # Refunds remain linked to their original sale; no fabricated fiscal receiptID.
        source_fields = ('id', 'company_id', 'shop_id', 'branch_id', 'device_id', 'employee_id', 'shift_id',
                         'original_sale_id', 'receipt_number', 'created_at', 'client_created_at', 'status',
                         'subtotal_amount', 'discount_amount', 'tax_amount', 'tax_rate', 'tax_inclusive',
                         'total_amount', 'payment_method', 'base_currency_code', 'payment_currency_code',
                         'payment_amount_original', 'refund_reason', 'refund_method')
        item_fields = ('id', 'product_id', 'variant_id', 'original_sale_item_id', 'product_name', 'quantity',
                       'unit_price', 'line_total', 'tax_rate_snapshot', 'tax_amount', 'tax_exempt_snapshot')
        def fields(obj, names):
            return {name: (value if value is None or isinstance(value, bool) else value.isoformat() if isinstance(value, datetime) else str(value))
                    for name in names for value in [getattr(obj, name)]}
        snapshot = {'kind': 'source_review_only', 'configuration_version': config.version,
                    'configuration_hash': digest(config.settings), 'sale': fields(sale, source_fields),
                    'items': [fields(item, item_fields) for item in items]}
        row = FiscalPreparation(company_id=self.company_id, sale_id=sale_id, snapshot=snapshot, snapshot_hash=digest(snapshot))
        self.db.add(row)
        await self.db.flush()
        self.audit('fiscal_source_prepared', {'preparation_id': str(row.id), 'sale_id': str(sale_id), 'snapshot_hash': row.snapshot_hash})
        await self.db.commit()
        return self.preparation_view(row)

    @staticmethod
    def preparation_view(row):
        if digest(row.snapshot) != row.snapshot_hash:
            raise HTTPException(409, 'Fiscal snapshot integrity check failed')
        return {'id': row.id, 'sale_id': row.sale_id, 'snapshot': row.snapshot,
                'sha256': row.snapshot_hash, 'state': 'review_only_not_fiscalised', 'submitted': False}

    async def preparations(self, offset=0):
        rows = (await self.db.execute(select(FiscalPreparation).where(FiscalPreparation.company_id == self.company_id)
                                     .order_by(FiscalPreparation.created_at.desc(), FiscalPreparation.id).offset(offset).limit(50))).scalars().all()
        return [self.preparation_view(row) for row in rows]

    async def audits(self, offset=0):
        rows = (await self.db.execute(select(FiscalAudit).where(FiscalAudit.company_id == self.company_id)
                                     .order_by(FiscalAudit.created_at.desc(), FiscalAudit.id).offset(offset).limit(50))).scalars().all()
        return [{'action': row.action, 'details': row.details, 'created_at': row.created_at} for row in rows]

    async def runtime_status(self, offset=0):
        state = await self.db.get(FiscalProtocolState, self.company_id)
        rows = (await self.db.execute(select(FiscalDocument, FiscalPreparation.sale_id).join(
            FiscalPreparation, FiscalPreparation.id == FiscalDocument.preparation_id).where(
            FiscalDocument.company_id == self.company_id, FiscalPreparation.company_id == self.company_id)
            .order_by(FiscalDocument.created_at.desc(), FiscalDocument.id).offset(offset).limit(50))).all()
        documents = []
        for row, sale_id in rows:
            events = (await self.db.execute(select(FiscalProtocolEvent).where(FiscalProtocolEvent.company_id == self.company_id,
                FiscalProtocolEvent.document_id == row.id).order_by(FiscalProtocolEvent.sequence))).scalars().all()
            ack = next((event for event in reversed(events) if event.kind == 'receipt_acknowledged'), None)
            documents.append({'id': row.id, 'sale_id': sale_id, 'day_no': row.day_no, 'global_no': row.global_no,
                              'status': 'acknowledged_test_validation_unknown' if ack else events[-1].kind if events else 'not_submitted',
                              'receipt_id': ack.details['receiptID'] if ack else None, 'environment': 'test',
                              'certified': False, 'sha256': row.payload_hash})
        data = state.data if state else {}
        return {'environment': 'test' if state else 'uncommissioned', 'submission_enabled': False,
                'certification': 'not_approved', 'day_status': data.get('status', 'not_initialised'),
                'day_no': data.get('day_no'), 'pending_operation': (data.get('pending') or {}).get('operation'),
                'documents': documents}
