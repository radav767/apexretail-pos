"""Management extensions to Phase 8. No tenant impersonation or secret serializers."""
from datetime import datetime,timezone,timedelta
from typing import Literal
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,Field,ConfigDict,field_validator
from sqlalchemy import select,func,text
from app.db.session import get_db
from app.models import Company,Branch,Employee,Device,Sale,CashierShift,CompanySubscription,CompanySubscriptionHistory
from app.models.commercial import PlatformAdmin,PlatformSession,PlatformSetting,PlatformAudit,BillingPlan
from app.models.fiscal import FiscalConfiguration,FiscalPreparation
from app.models.fiscal_protocol import FiscalProtocolState,FiscalProtocolEvent,FiscalDocument
from app.auth.security import hash_password
from .platform_auth import platform_actor,permit
from .commercial import CommercialService

router=APIRouter(tags=['Platform administration'])
UTC=timezone.utc
DEFAULTS={'brand_name':'ApexRetail','trial_days':30,'default_plan_id':None,'renewal_notices':True,
          'business_types':['Retail','Restaurant','Bar','Hospitality','Pharmacy','Wholesale','General']}

class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)

class SettingsInput(Strict):
    expected_version:int=Field(ge=0)
    brand_name:str=Field(min_length=1,max_length=80)
    trial_days:int=Field(ge=1,le=90)
    default_plan_id:UUID|None=None
    renewal_notices:bool=True
    business_types:list[str]=Field(min_length=1,max_length=30)
    @field_validator('business_types')
    @classmethod
    def types(cls,values):
        if len(set(values))!=len(values) or any(not v.strip() or len(v)>80 for v in values):raise ValueError('Unique non-empty business types required')
        return values

class AdminInput(Strict):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=False)
    email:str=Field(min_length=3,max_length=160,pattern=r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
    password:str=Field(min_length=12,max_length=72)
    role:Literal['super_admin','billing','support']
    @field_validator('password')
    @classmethod
    def password_size(cls,value):
        if len(value.encode())>72:raise ValueError('Password exceeds UTF-8 byte limit')
        return value

class AdminChange(Strict):
    role:Literal['super_admin','billing','support']
    active:bool
    reason:str=Field(min_length=3,max_length=500)

class Reason(Strict):
    reason:str=Field(min_length=3,max_length=500)

class TrialInput(Reason):
    expected_expiry:datetime
    expiry:datetime
    @field_validator('expected_expiry','expiry')
    @classmethod
    def aware(cls,value):
        if value.tzinfo is None:raise ValueError('Timezone required')
        return value

class DeviceAction(Reason):
    action:Literal['activate','revoke']
    offline_queue_resolved:bool=False
    active_checkout_closed:bool=False

def audit(db,admin,action,company=None,**details):
    db.add(PlatformAudit(admin_id=admin.id,company_id=company,action=action,details=details))

async def settings_values(db):
    row=await db.get(PlatformSetting,1)
    return {'version':row.version if row else 0,**DEFAULTS,**(row.values if row else {})}

@router.get('/settings')
async def settings(admin=Depends(platform_actor),db=Depends(get_db)):
    permit(admin,'read');return await settings_values(db)

@router.put('/settings')
async def save_settings(data:SettingsInput,admin=Depends(platform_actor),db=Depends(get_db)):
    permit(admin,'settings')
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext('platform-settings'))"))
    row=await db.get(PlatformSetting,1,populate_existing=True)
    if data.expected_version!=(row.version if row else 0):raise HTTPException(409,'Settings changed; reload first')
    if data.default_plan_id:
        plan=await db.get(BillingPlan,data.default_plan_id)
        if not plan or not plan.active:raise HTTPException(422,'Choose an active default plan')
    values=data.model_dump(mode='json',exclude={'expected_version'})
    if row:row.version+=1;row.values=values
    else:row=PlatformSetting(id=1,version=1,values=values);db.add(row)
    audit(db,admin,'platform_settings_saved',version=row.version,values=values)
    await db.commit();return await settings_values(db)

@router.get('/health')
async def health(admin=Depends(platform_actor),db=Depends(get_db)):
    permit(admin,'read');await db.execute(text('SELECT 1'))
    revision=(await db.execute(text('SELECT version_num FROM alembic_version'))).scalars().all()
    from .platform_mfa import cipher
    try:cipher();mfa='configured'
    except HTTPException:mfa='requires_provisioning'
    return {'api':'responding','database':'reachable','revision':revision,'mfa_key':mfa,
            'checked_at':datetime.now(UTC),'scope':'API/database only; not host, email or printer monitoring'}

@router.get('/businesses/{company_id}/details')
async def business_details(company_id:UUID,admin=Depends(platform_actor),db=Depends(get_db)):
    permit(admin,'read');company=await db.get(Company,company_id)
    if not company:raise HTTPException(404,'Business not found')
    counts={}
    for label,model in [('branches',Branch),('employees',Employee),('devices',Device),('sales',Sale),('shifts',CashierShift)]:
        counts[label]=(await db.execute(select(func.count(model.id)).where(model.company_id==company_id))).scalar_one()
    subscription=(await db.execute(select(CompanySubscription).where(CompanySubscription.company_id==company_id))).scalar_one_or_none()
    return {'id':company.id,'name':company.name,'email':company.owner_email,'business_type':company.business_type,
            'active':company.active,'deleted':company.deleted,'activity':counts,
            'trial_expiry':subscription.trial_ends_at if subscription and subscription.status=='trial' else None,
            'limits':{k:subscription.commercial_terms.get(k+'_limit') for k in ('branch','device','employee')} if subscription and subscription.commercial_terms else None,
            'recovery_policy':'Identity review only; no administrator password access or impersonation'}

@router.post('/businesses/{company_id}/recovery-review')
async def recovery(company_id:UUID,data:Reason,admin=Depends(platform_actor),db=Depends(get_db)):
    permit(admin,'recovery');await CommercialService(db,admin).company_lock(company_id)
    audit(db,admin,'business_recovery_review_requested',company_id,reason=data.reason,status='identity_review_pending')
    await db.commit()
    return {'status':'identity_review_pending','account_changed':False,
            'next_step':'Verify owner identity through the approved support procedure. No password reset or access token is issued.'}

@router.post('/businesses/{company_id}/trial')
async def trial(company_id:UUID,data:TrialInput,admin=Depends(platform_actor),db=Depends(get_db)):
    permit(admin,'trial');await CommercialService(db,admin).company_lock(company_id)
    sub=(await db.execute(select(CompanySubscription).where(CompanySubscription.company_id==company_id).with_for_update())).scalar_one_or_none()
    if not sub or sub.status!='trial':raise HTTPException(409,'Only existing trial subscriptions can be extended')
    if sub.trial_ends_at==data.expiry:return {'expiry':sub.trial_ends_at,'changed':False}
    if sub.trial_ends_at!=data.expected_expiry:raise HTTPException(409,'Trial changed; refresh before editing')
    now=datetime.now(UTC)
    if not sub.trial_ends_at<data.expiry or not now<data.expiry<=now+timedelta(days=90):raise HTTPException(422,'Trial extension must be in the next 90 days')
    old=sub.trial_ends_at
    grace=min(max((sub.grace_ends_at-old) if sub.grace_ends_at else timedelta(0),timedelta(0)),timedelta(hours=72))
    sub.trial_ends_at=data.expiry;sub.grace_ends_at=data.expiry+grace
    sub.status_reason=data.reason
    db.add(CompanySubscriptionHistory(company_subscription_id=sub.id,company_id=company_id,action='platform_trial_extended',plan=sub.plan,status=sub.status,
        provider=sub.provider,note=data.reason,payload={'old_expiry':old.isoformat(),'expiry':data.expiry.isoformat()}))
    audit(db,admin,'platform_trial_extended',company_id,old_expiry=old.isoformat(),expiry=data.expiry.isoformat(),reason=data.reason)
    await db.commit();return {'expiry':sub.trial_ends_at,'changed':True}

@router.get('/devices')
async def devices(search:str=Query('',max_length=160),company_id:UUID|None=None,
                  offset:int=Query(0,ge=0),admin=Depends(platform_actor),db=Depends(get_db)):
    permit(admin,'read')
    q=select(Device,Company.name).join(Company,Company.id==Device.company_id).where(Device.name.ilike('%'+search+'%'))
    if company_id:q=q.where(Device.company_id==company_id)
    rows=(await db.execute(q.order_by(Device.id).offset(offset).limit(100))).all()
    # Never serialize device keys, fingerprints or activation codes.
    return [{'id':d.id,'company_id':d.company_id,'business':name,'name':d.friendly_name or d.name,
             'status':d.status,'active':d.active,'removed':d.removed_at is not None,'branch_id':d.branch_id,
             'last_seen_at':d.last_seen_at,'app_version':d.last_seen_app_version or d.app_version} for d,name in rows]

@router.get('/devices/{device_id}/activity')
async def device_activity(device_id:UUID,company_id:UUID,admin=Depends(platform_actor),db=Depends(get_db)):
    permit(admin,'read')
    device=await db.get(Device,device_id)
    if not device or device.company_id!=company_id:raise HTTPException(404,'Device not found')
    from app.models import AuditEvent
    rows=(await db.execute(select(AuditEvent).where(AuditEvent.company_id==company_id,AuditEvent.device_id==device_id).order_by(AuditEvent.created_at.desc()).limit(100))).scalars().all()
    return [{'action':r.action,'created_at':r.created_at} for r in rows]

@router.post('/devices/{device_id}/status')
async def device_status(device_id:UUID,company_id:UUID,data:DeviceAction,admin=Depends(platform_actor),db=Depends(get_db)):
    permit(admin,'devices')
    # Same company lock as subscription capacity changes and normal device claims.
    await CommercialService(db,admin).company_lock(company_id)
    device=(await db.execute(select(Device).where(Device.id==device_id,Device.company_id==company_id).with_for_update())).scalar_one_or_none()
    if not device or device.removed_at or device.deleted:raise HTTPException(404,'Available device not found')
    if data.action=='activate':
        # Decommissioned terminals require the existing owner/device claim flow;
        # a platform toggle must not resurrect revoked offline authority.
        if device.deactivated_at or not device.claimed_at or device.status!='active' or not device.active:
            raise HTTPException(409,'Activation requires the existing business-owner registration and claim workflow')
        return {'status':'active','changed':False}
    if (await db.execute(select(CashierShift.id).where(CashierShift.device_id==device_id,CashierShift.status=='open').limit(1))).first():
        raise HTTPException(409,'Close the existing cashier shift before device revocation')
    from app.devices.service import DeviceService
    from app.devices.repository import DeviceRepository
    from app.devices.schema import DeviceDecommissionRequest
    audit(db,admin,'platform_device_revoked',company_id,device_id=str(device_id),reason=data.reason)
    await DeviceService(DeviceRepository(db)).decommission(company_id,device_id,
        DeviceDecommissionRequest(reason=data.reason,offline_queue_resolved=data.offline_queue_resolved,active_checkout_closed=data.active_checkout_closed),None)
    # decommission commits its audit and this platform audit atomically.
    await db.commit();return {'status':'deactivated'}

@router.get('/fiscal')
async def fiscal(company_id:UUID|None=None,offset:int=Query(0,ge=0),admin=Depends(platform_actor),db=Depends(get_db)):
    permit(admin,'read')
    q=select(Company,FiscalConfiguration,FiscalProtocolState).outerjoin(FiscalConfiguration,FiscalConfiguration.company_id==Company.id).outerjoin(FiscalProtocolState,FiscalProtocolState.company_id==Company.id)
    if company_id:q=q.where(Company.id==company_id)
    rows=(await db.execute(q.order_by(Company.id).offset(offset).limit(100))).all();result=[]
    for company,config,state in rows:
        counts={}
        for label,model in [('prepared',FiscalPreparation),('documents',FiscalDocument)]:
            counts[label]=(await db.execute(select(func.count()).select_from(model).where(model.company_id==company.id))).scalar_one()
        errors=(await db.execute(select(func.count(FiscalProtocolEvent.id)).where(FiscalProtocolEvent.company_id==company.id,FiscalProtocolEvent.kind.in_(['operation_rejected','operation_uncertain','receipt_status_inconclusive'])))).scalar_one()
        result.append({'company_id':company.id,'business':company.name,'configured':config is not None,
            'environment':config.settings.get('environment') if config else None,'device_registration':'test_protocol_initialized' if state else 'not_verified',
            'fiscal_day':state.data.get('status') if state else None,'pending_operation':bool(state and state.data.get('pending')),
            'counts':counts,'error_events':errors,'live_submission_enabled':False,'certification':'not_approved'})
    return result

def admin_view(row):
    return {'id':row.id,'email':row.email,'role':row.role,'active':row.active,'mfa_enrolled':bool(row.mfa_secret)}

async def lock_admin_management(db,admin):
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext('platform-admin-management'))"))
    # A root may have been disabled/demoted while waiting for this lock. Recheck
    # after serialization so two concurrent roots cannot disable one another.
    current=(await db.execute(select(PlatformAdmin).where(PlatformAdmin.id==admin.id).execution_options(populate_existing=True))).scalar_one_or_none()
    if not current or not current.active:raise HTTPException(403,'Administrator is unavailable')
    permit(current,'administrators')

@router.get('/administrators')
async def administrators(admin=Depends(platform_actor),db=Depends(get_db)):
    permit(admin,'administrators')
    return [admin_view(a) for a in (await db.execute(select(PlatformAdmin).order_by(PlatformAdmin.email).limit(200))).scalars()]

@router.post('/administrators')
async def create_admin(data:AdminInput,admin=Depends(platform_actor),db=Depends(get_db)):
    permit(admin,'administrators')
    await lock_admin_management(db,admin)
    if (await db.execute(select(PlatformAdmin.id).where(PlatformAdmin.email==data.email.lower()))).first():raise HTTPException(409,'Administrator already exists')
    row=PlatformAdmin(email=data.email.lower(),password_hash=hash_password(data.password),role=data.role)
    db.add(row);await db.flush();audit(db,admin,'platform_admin_created',administrator_id=str(row.id),role=row.role)
    await db.commit();return admin_view(row)

@router.put('/administrators/{admin_id}')
async def update_admin(admin_id:UUID,data:AdminChange,admin=Depends(platform_actor),db=Depends(get_db)):
    permit(admin,'administrators')
    await lock_admin_management(db,admin)
    if admin_id==admin.id:raise HTTPException(409,'Administrators cannot change their own role or availability')
    row=await db.get(PlatformAdmin,admin_id,populate_existing=True)
    if not row:raise HTTPException(404,'Administrator not found')
    row.role=data.role;row.active=data.active
    for session in (await db.execute(select(PlatformSession).where(PlatformSession.admin_id==admin_id,PlatformSession.revoked_at.is_(None)))).scalars():session.revoked_at=datetime.now(UTC)
    audit(db,admin,'platform_admin_updated',administrator_id=str(admin_id),role=data.role,active=data.active,reason=data.reason)
    await db.commit();return admin_view(row)

@router.get('/sessions')
async def sessions(admin=Depends(platform_actor),db=Depends(get_db)):
    q=select(PlatformSession).where(PlatformSession.revoked_at.is_(None),PlatformSession.expires_at>datetime.now(UTC))
    if admin.role!='super_admin':q=q.where(PlatformSession.admin_id==admin.id)
    return [{'id':s.id,'admin_id':s.admin_id,'expires_at':s.expires_at,'mfa_verified':s.mfa_verified} for s in (await db.execute(q.order_by(PlatformSession.expires_at.desc()).limit(200))).scalars()]

@router.post('/sessions/{session_id}/revoke')
async def revoke_session(session_id:UUID,admin=Depends(platform_actor),db=Depends(get_db)):
    row=await db.get(PlatformSession,session_id)
    if not row or admin.role!='super_admin' and row.admin_id!=admin.id:raise HTTPException(404,'Session not found')
    row.revoked_at=datetime.now(UTC);audit(db,admin,'platform_session_revoked',session_id=str(session_id))
    await db.commit();return {'ok':True}
