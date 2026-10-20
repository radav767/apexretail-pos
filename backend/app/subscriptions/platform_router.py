from datetime import datetime,timedelta,timezone
from uuid import UUID
from fastapi import APIRouter,Depends,Query
from sqlalchemy import select,func
from app.db.session import get_db
from app.auth.dependencies import get_auth_actor,ensure_company_access,require_path_owner,bearer_scheme
from app.models import Company,CompanySubscription,SubscriptionCheckoutSession
from app.models.commercial import BillingPayment,BillingInvoice,PlatformAudit,PlatformSession
from .commercial_schema import PlanInput,InvoiceInput,PaymentInput,LicenseInput,PlatformLogin,FEATURES
from .platform_auth import platform_actor,permit,login,authenticate
from .commercial import CommercialService,effective_status,terms_for

platform=APIRouter(prefix='/platform',tags=['Platform administration'])
business=APIRouter(prefix='/subscriptions',tags=['Commercial billing'])

@platform.post('/login')
async def platform_login(data:PlatformLogin,db=Depends(get_db)):return await login(db,data.email,data.password)

@platform.post('/logout')
async def platform_logout(admin=Depends(platform_actor),credentials=Depends(bearer_scheme),db=Depends(get_db)):
    _,session=await authenticate(db,credentials.credentials);session.revoked_at=datetime.now(timezone.utc)
    db.add(PlatformAudit(admin_id=admin.id,action='platform_logout',details={}));await db.commit();return {'ok':True}

@platform.get('/dashboard')
async def dashboard(admin=Depends(platform_actor),db=Depends(get_db)):
    permit(admin,'read')
    # No financial currency conversion or cross-currency summation.
    totals=(await db.execute(select(BillingInvoice.currency,func.sum(BillingPayment.amount)).join(BillingPayment,BillingPayment.invoice_id==BillingInvoice.id).group_by(BillingInvoice.currency))).all()
    legacy=(await db.execute(select(SubscriptionCheckoutSession.billing_currency,func.sum(SubscriptionCheckoutSession.total_amount)).where(
        SubscriptionCheckoutSession.status=='paid',SubscriptionCheckoutSession.billing_currency.is_not(None),SubscriptionCheckoutSession.total_amount.is_not(None)).group_by(SubscriptionCheckoutSession.billing_currency))).all()
    revenue={}
    for currency,amount in [*totals,*legacy]:revenue[currency]=revenue.get(currency,0)+amount
    subs=(await db.execute(select(CompanySubscription))).scalars().all()
    counts={name:0 for name in ('active','trial','expired','grace_period','suspended','cancelled','unconfigured')}
    now=datetime.now(timezone.utc);upcoming=0
    for sub in subs:
        status=effective_status(sub);counts[status]=counts.get(status,0)+1
        end=sub.trial_ends_at if status=='trial' else sub.current_period_ends_at
        if end and now<=end<=now+timedelta(days=30):upcoming+=1
    return {'businesses':(await db.execute(select(func.count(Company.id)))).scalar_one(),'subscriptions':counts,'upcoming_renewals':upcoming,
        'revenue':[{'currency':c,'amount':a} for c,a in sorted(revenue.items())],
        'revenue_sources':['confirmed_manual_invoice_payments','verified_paid_legacy_checkouts']}

@platform.get('/businesses')
async def companies(search:str=Query(default='',max_length=160),offset:int=Query(default=0,ge=0),admin=Depends(platform_actor),db=Depends(get_db)):
    permit(admin,'read')
    rows=(await db.execute(select(Company,CompanySubscription).outerjoin(CompanySubscription,CompanySubscription.company_id==Company.id)
        .where(Company.name.ilike('%'+search+'%')).order_by(Company.id).offset(offset).limit(100))).all()
    return [{'id':c.id,'name':c.name,'email':c.owner_email,'status':effective_status(s),'terms':s.commercial_terms if s else None,
        'activation_date':s.current_period_started_at if s else None,'expiry_date':s.current_period_ends_at if s else None} for c,s in rows]

@platform.get('/plans')
async def plans(admin=Depends(platform_actor),db=Depends(get_db)):
    permit(admin,'read');return await CommercialService(db,admin).plans()

@platform.post('/plans')
async def create_plan(data:PlanInput,admin=Depends(platform_actor),db=Depends(get_db)):return await CommercialService(db,admin).save_plan(data)

@platform.put('/plans/{plan_id}')
async def update_plan(plan_id:UUID,data:PlanInput,admin=Depends(platform_actor),db=Depends(get_db)):return await CommercialService(db,admin).save_plan(data,plan_id)

@platform.post('/invoices')
async def invoice(data:InvoiceInput,admin=Depends(platform_actor),db=Depends(get_db)):return await CommercialService(db,admin).issue(data)

@platform.post('/payments')
async def payment(data:PaymentInput,admin=Depends(platform_actor),db=Depends(get_db)):return await CommercialService(db,admin).confirm(data)

@platform.get('/businesses/{company_id}/billing')
async def billing(company_id:UUID,offset:int=Query(default=0,ge=0),admin=Depends(platform_actor),db=Depends(get_db)):
    permit(admin,'read');return await CommercialService(db,admin).billing(company_id,offset)

@platform.post('/businesses/{company_id}/license')
async def license_action(company_id:UUID,data:LicenseInput,admin=Depends(platform_actor),db=Depends(get_db)):return await CommercialService(db,admin).license_action(company_id,data)

@platform.post('/notifications/generate')
async def notifications(admin=Depends(platform_actor),db=Depends(get_db)):return await CommercialService(db,admin).reminders()

@platform.get('/audit')
async def audit(admin=Depends(platform_actor),db=Depends(get_db)):
    permit(admin,'read');return (await db.execute(select(PlatformAudit).order_by(PlatformAudit.created_at.desc()).limit(200))).scalars().all()

@business.get('/access/{company_id}')
async def access(company_id:UUID,actor=Depends(get_auth_actor),db=Depends(get_db)):
    ensure_company_access(actor,company_id);terms=await terms_for(db,company_id)
    return {'managed':terms is not None,'features':terms.get('features',{}) if terms else {f:True for f in FEATURES},
        'limits':{k:terms.get(k+'_limit') if terms else None for k in ('branch','device','employee')}}

@business.get('/billing/{company_id}')
async def business_billing(company_id:UUID,offset:int=Query(default=0,ge=0),actor=Depends(require_path_owner),db=Depends(get_db)):
    return await CommercialService(db).billing(company_id,offset)
