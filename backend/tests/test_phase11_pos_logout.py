"""Legacy employee/user and opaque POS revocation on synthetic rollback fixtures."""
import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import httpx
import jwt
from sqlalchemy import select
from app.auth.security import create_access_token, create_employee_access_token, hash_session_token
from app.core.config import get_settings
from app.db.session import get_db
from app.main import app
from app.models import CompanySubscription, PosSession, Company, User, AuditEvent
import test_phase7d_operations as fixtures


class PosLogoutTests(unittest.IsolatedAsyncioTestCase):
    cleanup = fixtures.Phase7DOperationsTests.cleanup

    async def asyncSetUp(self):
        await fixtures.Phase7DOperationsTests.asyncSetUp(self)
        self.opaque = 'synthetic-opaque-'+str(uuid4()); self.session.token_hash = hash_session_token(self.opaque)
        await self.db.commit()
        async def override(): yield self.db
        app.dependency_overrides[get_db] = override; self.addCleanup(app.dependency_overrides.clear)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://synthetic.test')
        self.addAsyncCleanup(self.client.aclose)

    def headers(self, token): return {'Authorization':'Bearer '+token}
    def employee_token(self, version=0):
        return create_employee_access_token(employee_id=str(self.employee.id),company_id=str(self.company.id),role=self.employee.role,session_version=version)
    async def read(self, token):
        return await self.client.get('/api/employees/permissions/catalog',headers=self.headers(token))
    async def logout(self, token, owner=None):
        return await self.client.post('/api/employees/session/logout',headers=self.headers(token),json={'cached_user_token':owner} if owner else {})

    async def test_employee_logout_revokes_opaque_current_and_legacy_jwt_even_when_expired(self):
        settings=get_settings(); legacy=jwt.encode({'sub':str(self.employee.id),'company_id':str(self.company.id),'token_type':'employee',
            'exp':datetime.now(timezone.utc)+timedelta(minutes=5)},settings.jwt_secret,algorithm=settings.jwt_algorithm)
        current=self.employee_token()
        for token in (self.opaque,current,legacy): self.assertEqual((await self.read(token)).status_code,200)
        sub=(await self.db.execute(select(CompanySubscription).where(CompanySubscription.company_id==self.company.id))).scalar_one()
        sub.status='expired';await self.db.commit()
        self.assertEqual((await self.logout(self.opaque)).status_code,200)
        await self.db.refresh(self.employee);self.assertEqual(self.employee.session_version,1)
        for token in (self.opaque,current,legacy): self.assertEqual((await self.read(token)).status_code,401)
        self.assertEqual((await self.read(self.employee_token(1))).status_code,200)

    async def test_pos_user_logout_revokes_legacy_and_current_owner_tokens(self):
        settings=get_settings(); legacy=jwt.encode({'sub':str(self.user.id),'exp':datetime.now(timezone.utc)+timedelta(minutes=5)},settings.jwt_secret,algorithm=settings.jwt_algorithm)
        current=create_access_token(str(self.user.id),self.user.email)
        self.assertEqual((await self.logout(current)).status_code,200)
        for token in (current,legacy): self.assertEqual((await self.read(token)).status_code,401)
        await self.db.refresh(self.user);self.assertEqual(self.user.session_version,1)
        self.assertEqual(self.employee.session_version,0)

    async def test_full_employee_logout_can_only_revoke_cached_same_business_owner(self):
        owner=create_access_token(str(self.user.id),self.user.email)
        response=await self.logout(self.opaque,owner);self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json(),{'ok':True})
        self.assertEqual((await self.read(owner)).status_code,401)
        self.assertEqual((await self.read(self.opaque)).status_code,401)
        audits=(await self.db.execute(select(AuditEvent).where(AuditEvent.company_id==self.company.id,AuditEvent.action=='business_user_sessions_revoked'))).scalars().all()
        self.assertEqual(len(audits),1);self.assertNotIn(owner,str(audits[0].details))

    async def test_cashier_switch_keeps_owner_and_foreign_owner_is_denied(self):
        owner=create_access_token(str(self.user.id),self.user.email)
        other_company=Company(name='Synthetic other business',owner_email=f'{uuid4()}@example.test');self.db.add(other_company);await self.db.flush()
        other=User(company_id=other_company.id,email=f'{uuid4()}@example.test',password_hash='unused',role='owner');self.db.add(other);await self.db.commit()
        foreign=create_access_token(str(other.id),other.email)
        self.assertEqual((await self.logout(self.opaque,foreign)).status_code,403)
        self.assertEqual((await self.read(foreign)).status_code,200)
        self.assertEqual((await self.read(self.opaque)).status_code,200)
        self.assertEqual((await self.logout(self.opaque)).status_code,200)
        self.assertEqual((await self.read(owner)).status_code,200)

    async def test_stale_pin_transaction_cannot_resurrect_after_logout_and_new_pin_works(self):
        old_version=self.employee.session_version
        self.assertEqual((await self.logout(self.opaque)).status_code,200)
        stale='synthetic-stale-'+str(uuid4())
        self.db.add(PosSession(company_id=self.company.id,employee_id=self.employee.id,device_id=self.device.id,shop_id=self.shop.id,
            branch_id=self.branch.id,session_version=old_version,token_hash=hash_session_token(stale),expires_at=datetime.now(timezone.utc)+timedelta(hours=12)))
        await self.db.commit()
        self.assertEqual((await self.read(stale)).status_code,401)
        fresh=await self.client.post('/api/employees/pin-login',json={'company_id':str(self.company.id),'branch_id':str(self.branch.id),
            'shop_id':str(self.shop.id),'device_id':str(self.device.id),'device_key':self.device.device_key,'pin':'1234','session_token':stale})
        self.assertEqual(fresh.status_code,200,fresh.text)
        token=fresh.json()['access_token'];self.assertNotEqual(token,stale)
        self.assertEqual((await self.read(token)).status_code,200)
        self.assertEqual((await self.read(stale)).status_code,401)

    async def test_employee_version_values_are_strict(self):
        settings=get_settings()
        for version in (None,True,False,'0',-1,0.0):
            token=jwt.encode({'sub':str(self.employee.id),'company_id':str(self.company.id),'token_type':'employee','session_version':version,
                'exp':datetime.now(timezone.utc)+timedelta(minutes=5)},settings.jwt_secret,algorithm=settings.jwt_algorithm)
            self.assertEqual((await self.read(token)).status_code,401)
