"""Opt-in commercial policy, invoices and exactly-once paid renewals."""
import calendar
import hashlib
import json
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import select,func
from sqlalchemy.exc import IntegrityError
from fastapi.encoders import jsonable_encoder
from app.models import Company,CompanySubscription,CompanySubscriptionHistory,Branch,Device,Employee
from app.models.commercial import BillingPlan,BillingInvoice,BillingPayment,BillingNotice,PlatformAudit
from .commercial_schema import FEATURES
from .platform_auth import permit

UTC=timezone.utc
def add_months(value,months):
    year,month=divmod(value.year*12+value.month-1+months,12)
    return value.replace(year=year,month=month+1,day=min(value.day,calendar.monthrange(year,month+1)[1]))
def digest(value):return hashlib.sha256(json.dumps(jsonable_encoder(value),sort_keys=True,separators=(',',':')).encode()).hexdigest()
def effective_status(sub,now=None):
    if sub is None:return 'unconfigured'
    now=now or datetime.now(UTC)
    if sub.status in {'suspended','cancelled','canceled'}:return sub.status
    end=sub.trial_ends_at if sub.status=='trial' else sub.current_period_ends_at or sub.trial_ends_at
    if end and now>end:return 'grace_period' if sub.grace_ends_at and now<=sub.grace_ends_at else 'expired'
    return sub.status

async def terms_for(db,company_id):
    return (await db.execute(select(CompanySubscription.commercial_terms).where(CompanySubscription.company_id==company_id))).scalar_one_or_none()

async def enforce_feature(db,company_id,feature):
    terms=await terms_for(db,company_id)
    if terms is not None and not terms.get('features',{}).get(feature,False):raise HTTPException(403,'Subscription does not include '+feature)

async def enforce_capacity(db,company_id,kind,exclude_id=None):
    terms=await terms_for(db,company_id)
    if terms is None:return
    # Serialize capacity checks with normal creation and paid plan changes.
    await db.execute(select(Company.id).where(Company.id==company_id).with_for_update())
    terms=await terms_for(db,company_id)
    limit=terms.get(kind+'_limit') if terms else None
    if limit is None:return
    model={'branch':Branch,'device':Device,'employee':Employee}[kind]
    q=select(func.count(model.id)).where(model.company_id==company_id,model.active==True,model.deleted==False)
    if kind=='device':q=q.where(Device.status=='active',Device.claimed_at.is_not(None),Device.removed_at.is_(None),Device.deactivated_at.is_(None))
    if exclude_id:q=q.where(model.id!=exclude_id)
    if (await db.execute(q)).scalar_one()>=limit:raise HTTPException(402,f'Subscription {kind} limit reached')

async def validate_existing_usage(db,company_id,terms):
    for kind,model in (('branch',Branch),('device',Device),('employee',Employee)):
        limit=terms.get(kind+'_limit')
        if limit is None:continue
        q=select(func.count(model.id)).where(model.company_id==company_id,model.active==True,model.deleted==False)
        if kind=='device':q=q.where(Device.status=='active',Device.claimed_at.is_not(None),Device.removed_at.is_(None),Device.deactivated_at.is_(None))
        if (await db.execute(q)).scalar_one()>limit:raise HTTPException(409,f'Existing {kind} usage exceeds this plan. Select adequate limits; no existing records were disabled.')

class CommercialService:
    def __init__(self,db,admin=None):self.db=db;self.admin=admin
    def audit(self,action,company=None,**details):
        self.db.add(PlatformAudit(admin_id=self.admin.id if self.admin else None,company_id=company,action=action,details=jsonable_encoder(details)))
    async def company_lock(self,company):
        row=(await self.db.execute(select(Company).where(Company.id==company).with_for_update())).scalar_one_or_none()
        if not row:raise HTTPException(404,'Business not found')
        return row
    async def plans(self):return (await self.db.execute(select(BillingPlan).order_by(BillingPlan.name))).scalars().all()
    async def save_plan(self,data,plan_id=None):
        permit(self.admin,'plans')
        row=(await self.db.execute(select(BillingPlan).where(BillingPlan.id==plan_id).with_for_update())).scalar_one_or_none() if plan_id else BillingPlan(version=1)
        if not row:raise HTTPException(404,'Plan not found')
        if plan_id and data.expected_version!=row.version:raise HTTPException(409,'Plan changed; reload before editing')
        if plan_id:row.version+=1
        row.name=data.name.strip();row.active=data.active
        row.terms=data.model_dump(mode='json',exclude={'name','active','expected_version'})
        row.terms['features']={key:bool(data.features.get(key,False)) for key in FEATURES}
        self.db.add(row);await self.db.flush();self.audit('billing_plan_saved',plan_id=row.id,version=row.version,terms=row.terms)
        await self.db.commit();return row
    async def issue(self,data):
        permit(self.admin,'invoice');await self.company_lock(data.company_id)
        fingerprint=digest(data.model_dump(mode='json'))
        old=(await self.db.execute(select(BillingInvoice).where(BillingInvoice.company_id==data.company_id,BillingInvoice.request_id==data.request_id))).scalar_one_or_none()
        if old:
            if old.payload_hash!=fingerprint:raise HTTPException(409,'Invoice request changed')
            return old
        plan=await self.db.get(BillingPlan,data.plan_id)
        if not plan or not plan.active:raise HTTPException(404,'Active plan not found')
        await validate_existing_usage(self.db,data.company_id,plan.terms)
        amount=data.custom_amount if data.custom_amount is not None else Decimal(plan.terms['price'])
        if amount!=amount.quantize(Decimal(1).scaleb(-plan.terms['decimal_places'])):raise HTTPException(422,'Amount exceeds invoice currency precision')
        snapshot={**plan.terms,'price':str(amount),'plan_name':plan.name,'plan_version':plan.version,'plan_id':str(plan.id),'reason':data.reason}
        invoice=BillingInvoice(company_id=data.company_id,request_id=data.request_id,payload_hash=fingerprint,plan_id=plan.id,
            snapshot=snapshot,amount=amount,currency=plan.terms['currency'],decimal_places=plan.terms['decimal_places'],due_at=data.due_at)
        self.db.add(invoice);await self.db.flush();self.audit('billing_invoice_issued',data.company_id,invoice_id=invoice.id,reason=data.reason)
        await self.db.commit();return invoice
    async def paid(self,invoice):
        return (await self.db.execute(select(func.coalesce(func.sum(BillingPayment.amount),0)).where(BillingPayment.invoice_id==invoice.id))).scalar_one()
    async def confirm(self,data):
        permit(self.admin,'payment');await self.company_lock(data.company_id)
        invoice=(await self.db.execute(select(BillingInvoice).where(BillingInvoice.id==data.invoice_id,BillingInvoice.company_id==data.company_id).with_for_update())).scalar_one_or_none()
        if not invoice:raise HTTPException(404,'Invoice not found')
        old=(await self.db.execute(select(BillingPayment).where(BillingPayment.company_id==data.company_id,BillingPayment.request_id==data.request_id))).scalar_one_or_none()
        if old:
            if old.invoice_id!=invoice.id or old.amount!=data.amount or old.method!=data.method or old.reference!=data.reference.strip():raise HTTPException(409,'Payment request changed')
            return old
        if not data.reference.strip():raise HTTPException(422,'Payment reference required')
        from app.models import SubscriptionCheckoutSession
        legacy=(await self.db.execute(select(SubscriptionCheckoutSession.id).where(SubscriptionCheckoutSession.company_id==data.company_id,
            SubscriptionCheckoutSession.status=='paid',((SubscriptionCheckoutSession.paynow_reference==data.reference.strip())|
            (SubscriptionCheckoutSession.session_reference==data.reference.strip()))).limit(1))).first()
        if legacy:raise HTTPException(409,'This reference is already a hosted payment; use reviewed reconciliation, not another receipt')
        if (await self.db.execute(select(BillingPayment.id).where(BillingPayment.company_id==data.company_id,BillingPayment.reference==data.reference.strip()))).first():raise HTTPException(409,'Payment reference already confirmed')
        paid=await self.paid(invoice)
        if data.amount!=data.amount.quantize(Decimal(1).scaleb(-invoice.decimal_places)):raise HTTPException(422,'Amount exceeds invoice currency precision')
        if invoice.fulfilled_at or paid+data.amount>invoice.amount:raise HTTPException(409,'Payment exceeds outstanding invoice balance')
        if paid+data.amount==invoice.amount:await validate_existing_usage(self.db,data.company_id,invoice.snapshot)
        sub=(await self.db.execute(select(CompanySubscription).where(CompanySubscription.company_id==data.company_id).with_for_update())).scalar_one_or_none()
        if not sub:raise HTTPException(409,'Business subscription must be initialized through registration')
        if sub.commercial_terms is None:
            from app.models import SubscriptionCheckoutSession
            pending=(await self.db.execute(select(SubscriptionCheckoutSession.id).where(SubscriptionCheckoutSession.company_id==data.company_id,
                SubscriptionCheckoutSession.status.notin_(['paid','failed','cancelled','canceled','expired'])).limit(1))).first()
            if pending:raise HTTPException(409,'Reconcile pending hosted checkouts before switching to commercial billing')
        # A payment never silently reactivates an explicitly suspended license.
        if effective_status(sub) in {'suspended','cancelled','canceled'}:raise HTTPException(409,'Resolve license suspension before confirming renewal')
        payment=BillingPayment(company_id=data.company_id,invoice_id=invoice.id,request_id=data.request_id,admin_id=self.admin.id,amount=data.amount,method=data.method,reference=data.reference.strip())
        self.db.add(payment)
        if paid+data.amount==invoice.amount:
            now=datetime.now(UTC);start=max(now,sub.current_period_ends_at or now)
            end=add_months(start,int(invoice.snapshot['months']))
            sub.commercial_terms={**invoice.snapshot,'offline_grace_hours':min(int(invoice.snapshot['offline_grace_hours']),72)}
            sub.plan='commercial';sub.status='active';sub.current_period_started_at=start;sub.current_period_ends_at=end
            sub.grace_ends_at=end+timedelta(hours=sub.commercial_terms['offline_grace_hours'])
            sub.provider='manual';sub.provider_reference=str(invoice.id);sub.billing_currency=invoice.currency
            # Legacy summary amounts are NUMERIC(12,2). Do not round a new
            # 0–4 decimal invoice into them or rewrite prior provider summaries.
            sub.licensed_terminal_count=invoice.snapshot.get('device_limit');invoice.fulfilled_at=now
            self.db.add(CompanySubscriptionHistory(company_subscription_id=sub.id,company_id=sub.company_id,action='commercial_renewed',
                plan='commercial',status='active',provider='manual',provider_reference=str(invoice.id),payload=jsonable_encoder({'invoice_id':invoice.id,'start':start,'end':end,'terms':sub.commercial_terms}),note=data.reason))
            self.notice(sub.company_id,'payment:'+str(invoice.id),'payment_confirmation',f'Invoice {invoice.id} paid in {invoice.currency}. License renewed until {end.isoformat()}.')
        self.audit('billing_payment_confirmed',data.company_id,invoice_id=invoice.id,amount=str(data.amount),reference=data.reference.strip(),reason=data.reason)
        try:await self.db.commit()
        except IntegrityError:
            await self.db.rollback();raise HTTPException(409,'Payment identity or reference already exists; review original receipt')
        return payment
    def notice(self,company,key,kind,message):self.db.add(BillingNotice(company_id=company,event_key=key,kind=kind,message=message))
    async def license_action(self,company,data):
        permit(self.admin,'license');await self.company_lock(company)
        sub=(await self.db.execute(select(CompanySubscription).where(CompanySubscription.company_id==company).with_for_update())).scalar_one_or_none()
        if not sub:raise HTTPException(404,'Subscription not found')
        if data.action=='reactivate':
            now=datetime.now(UTC)
            if not sub.current_period_ends_at or sub.current_period_ends_at<=now:raise HTTPException(409,'Paid subscription period has expired; renew before reactivation')
            sub.status='active'
        else:sub.status='suspended'
        sub.status_reason=data.reason
        self.db.add(CompanySubscriptionHistory(company_subscription_id=sub.id,company_id=company,action='license_'+data.action,plan=sub.plan,status=sub.status,provider=sub.provider,note=data.reason))
        self.audit('license_'+data.action,company,reason=data.reason);await self.db.commit()
        return {'status':effective_status(sub)}
    async def billing(self,company,offset=0):
        sub=(await self.db.execute(select(CompanySubscription).where(CompanySubscription.company_id==company))).scalar_one_or_none()
        paid=select(BillingPayment.invoice_id,func.sum(BillingPayment.amount).label('paid')).group_by(BillingPayment.invoice_id).subquery()
        amount_paid=func.coalesce(paid.c.paid,0)
        invoices=(await self.db.execute(select(BillingInvoice,amount_paid).outerjoin(paid,paid.c.invoice_id==BillingInvoice.id).where(BillingInvoice.company_id==company).order_by(BillingInvoice.created_at.desc(),BillingInvoice.id).offset(offset).limit(200))).all()
        payments=(await self.db.execute(select(BillingPayment,BillingInvoice.currency).join(BillingInvoice,BillingInvoice.id==BillingPayment.invoice_id).where(BillingPayment.company_id==company).order_by(BillingPayment.created_at.desc(),BillingPayment.id).offset(offset).limit(200))).all()
        totals=(await self.db.execute(select(BillingInvoice.currency,func.sum(BillingInvoice.amount-amount_paid)).outerjoin(paid,paid.c.invoice_id==BillingInvoice.id).where(BillingInvoice.company_id==company).group_by(BillingInvoice.currency))).all()
        invoice_count=(await self.db.execute(select(func.count(BillingInvoice.id)).where(BillingInvoice.company_id==company))).scalar_one()
        payment_count=(await self.db.execute(select(func.count(BillingPayment.id)).where(BillingPayment.company_id==company))).scalar_one()
        return {'subscription':{'status':effective_status(sub),'terms':sub.commercial_terms if sub else None,'activation_date':sub.current_period_started_at if sub else None,'expiry_date':sub.current_period_ends_at if sub else None},
            'offset':offset,'has_more':max(invoice_count,payment_count)>offset+200,'outstanding_by_currency':[{'currency':c,'amount':a} for c,a in totals],
            'invoices':[{'id':r.id,'amount':r.amount,'currency':r.currency,'decimal_places':r.decimal_places,'due_at':r.due_at,'created_at':r.created_at,'plan':r.snapshot,'paid':p,'outstanding':r.amount-p,'fulfilled_at':r.fulfilled_at} for r,p in invoices],
            'payments':[{'id':p.id,'invoice_id':p.invoice_id,'amount':p.amount,'currency':currency,'method':p.method,'reference':p.reference,'created_at':p.created_at} for p,currency in payments],
            'notices':(await self.db.execute(select(BillingNotice).where(BillingNotice.company_id==company).order_by(BillingNotice.created_at.desc()).limit(100))).scalars().all()}
    async def reminders(self):
        if self.admin is not None:permit(self.admin,'notifications')
        # Serialize generation to make repeated scheduler/manual invocations safe.
        from sqlalchemy import text
        await self.db.execute(text('SELECT pg_advisory_xact_lock(80808008)'))
        rows=(await self.db.execute(select(CompanySubscription))).scalars().all();count=0;now=datetime.now(UTC)
        for sub in rows:
            end=sub.trial_ends_at if sub.status=='trial' else sub.current_period_ends_at or sub.trial_ends_at
            if not end or effective_status(sub) in {'suspended','cancelled','canceled'}:continue
            days=(end-now).total_seconds()/86400
            kind='expiration' if days<=0 else 'trial_expiry' if sub.status=='trial' else 'renewal'
            if days>7:continue
            key=f'{sub.company_id}:{kind}:{end.isoformat()}'
            if (await self.db.execute(select(BillingNotice.id).where(BillingNotice.event_key==key))).first():continue
            self.notice(sub.company_id,key,kind,f'Subscription {kind.replace("_"," ")}: {end.isoformat()}. Business records are retained.');count+=1
        self.audit('billing_reminders_generated',count=count);await self.db.commit();return {'created':count,'channel':'in_app','external_delivery':'not_configured'}
