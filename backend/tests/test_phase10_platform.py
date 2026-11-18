"""Existing rollback-only PostgreSQL fixtures; no live credentials or tenant writes."""
import base64,time,unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
from uuid import uuid4
import httpx
from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy import select,func,text
from sqlalchemy.exc import DBAPIError
from app.auth.security import hash_password,hash_session_token,create_access_token
from app.models import CompanySubscription,Device
from app.models.commercial import PlatformAdmin,PlatformSession,PlatformAudit,PlatformSetting,PlatformChallenge
from app.models.fiscal import FiscalConfiguration
from app.subscriptions.platform_auth import login,authenticate
from app.subscriptions.platform_mfa import totp,verify
from app.subscriptions.service import SubscriptionService
import test_phase7d_operations as fixtures

UTC=timezone.utc

class TOTPVectors(unittest.TestCase):
    def test_rfc6238_sha1_vectors(self):
        secret=base64.b32encode(b'12345678901234567890').decode()
        for timestamp,value in [(59,'94287082'),(1111111109,'07081804'),(1111111111,'14050471'),(1234567890,'89005924'),(2000000000,'69279037'),(20000000000,'65353130')]:
            with self.subTest(timestamp=timestamp):self.assertEqual(totp(secret,timestamp//30,8),value)

class PlatformTests(unittest.IsolatedAsyncioTestCase):
    cleanup=fixtures.Phase7DOperationsTests.cleanup
    async def asyncSetUp(self):
        await fixtures.Phase7DOperationsTests.asyncSetUp(self)
        self.key=Fernet.generate_key().decode()
        self.env=patch.dict('os.environ',{'PLATFORM_MFA_KEY':self.key});self.env.start();self.addCleanup(self.env.stop)
        self.admin=PlatformAdmin(email=f'{uuid4()}@platform.test',password_hash=hash_password('synthetic-admin-password'),role='super_admin')
        self.db.add(self.admin);await self.db.commit()
        self.now=1800000000
    async def token(self,admin=None):
        admin=admin or self.admin
        result=await login(self.db,admin.email,'synthetic-admin-password')
        self.secret=result.get('secret') or Fernet(self.key.encode()).decrypt(admin.mfa_secret.encode()).decode()
        self.now=max(self.now,30*(admin.mfa_last_step+1))
        with patch('app.subscriptions.platform_mfa.time.time',return_value=self.now):
            return (await verify(self.db,result['challenge'],totp(self.secret,self.now//30)))['access_token']
    async def client(self,token=None):
        from app.main import app
        from app.db.session import get_db
        async def override():yield self.db
        app.dependency_overrides[get_db]=override;self.addCleanup(app.dependency_overrides.clear)
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://isolated.test',headers={'Authorization':'Bearer '+(token or await self.token())})
    async def test_password_alone_never_authorizes_and_replay_is_rejected(self):
        challenge=await login(self.db,self.admin.email,'synthetic-admin-password')
        self.assertNotIn('access_token',challenge)
        with self.assertRaises(HTTPException):await authenticate(self.db,challenge['challenge'])
        with patch('app.subscriptions.platform_mfa.time.time',return_value=self.now):
            code=totp(challenge['secret'],self.now//30)
            auth=await verify(self.db,challenge['challenge'],code)
            self.assertEqual((await authenticate(self.db,auth['access_token']))[0].id,self.admin.id)
            with self.assertRaises(HTTPException):await verify(self.db,challenge['challenge'],code)
            second=await login(self.db,self.admin.email,'synthetic-admin-password')
            with self.assertRaises(HTTPException):await verify(self.db,second['challenge'],code)
        self.assertNotIn(challenge['secret'],self.admin.mfa_secret)
    async def test_mfa_failures_cannot_reset_budget_with_correct_password(self):
        challenge=await login(self.db,self.admin.email,'synthetic-admin-password')
        for i in range(5):
            with patch('app.subscriptions.platform_mfa.time.time',return_value=self.now):
                code='000000'
                if any(totp(challenge['secret'],self.now//30+d)==code for d in [-1,0,1]):code='000001'
                with self.assertRaises(HTTPException):await verify(self.db,challenge['challenge'],code)
            if i<4:challenge=await login(self.db,self.admin.email,'synthetic-admin-password')
        with self.assertRaises(HTTPException):await login(self.db,self.admin.email,'synthetic-admin-password')
    async def test_expired_challenge_missing_key_and_old_sessions_fail_closed(self):
        challenge=await login(self.db,self.admin.email,'synthetic-admin-password')
        row=(await self.db.execute(select(PlatformChallenge).where(PlatformChallenge.admin_id==self.admin.id))).scalar_one()
        row.expires_at=datetime.now(UTC)-timedelta(seconds=1);await self.db.commit()
        with self.assertRaises(HTTPException):await verify(self.db,challenge['challenge'],'123456')
        with patch.dict('os.environ',{'PLATFORM_MFA_KEY':''}):
            with self.assertRaises(HTTPException) as error:await login(self.db,self.admin.email,'synthetic-admin-password')
            self.assertEqual(error.exception.status_code,503)
        raw='apx_platform_'+str(uuid4());self.db.add(PlatformSession(admin_id=self.admin.id,token_hash=hash_session_token(raw),expires_at=datetime.now(UTC)+timedelta(minutes=30),mfa_verified=False));await self.db.commit()
        with self.assertRaises(HTTPException):await authenticate(self.db,raw)
    async def test_dashboard_counts_health_and_secret_free_summaries(self):
        self.db.add(FiscalConfiguration(company_id=self.company.id,version=1,settings={'environment':'test','credential_reference':'MUST-NOT-LEAK'}));await self.db.commit()
        async with await self.client() as client:
            dashboard=(await client.get('/api/platform/dashboard')).json()
            for key in ('businesses','active_businesses','suspended_businesses','registered_devices','upcoming_renewals'):self.assertGreaterEqual(dashboard[key],0)
            from app.models import Company
            self.assertEqual(dashboard['businesses'],(await self.db.execute(select(func.count(Company.id)))).scalar_one())
            detail=await client.get(f'/api/platform/businesses/{self.company.id}/details');self.assertEqual(detail.status_code,200);self.assertEqual(detail.json()['activity']['sales'],1)
            fiscal=await client.get(f'/api/platform/fiscal?company_id={self.company.id}');self.assertEqual(fiscal.status_code,200);self.assertNotIn('MUST-NOT-LEAK',fiscal.text);self.assertFalse(fiscal.json()[0]['live_submission_enabled'])
            devices=await client.get('/api/platform/devices');self.assertEqual(devices.status_code,200)
            self.assertNotIn('device_key',devices.text);self.assertNotIn('activation_code',devices.text)
            self.assertEqual((await client.get('/api/platform/health')).json()['database'],'reachable')
    async def test_login_responses_are_not_cacheable_and_config_secret_is_masked(self):
        async with await self.client() as client:
            response=await client.post('/api/platform/login',json={'email':self.admin.email,'password':'synthetic-admin-password'})
            self.assertEqual(response.status_code,200);self.assertEqual(response.headers['cache-control'],'no-store')
            self.assertNotIn('access_token',response.json())
            self.assertEqual((await client.post('/api/platform/mfa',json={'challenge':response.json()['challenge'],'code':'١٢٣٤٥٦'})).status_code,422)
        from app.subscriptions.platform_mfa import cipher
        from app.core.config import Settings
        configured=Settings(database_url='postgresql://postgres@/isolated_test',jwt_secret='synthetic-phase11-config-test-secret-123456789',platform_mfa_key=self.key,_env_file=None)
        self.assertNotIn(self.key,repr(configured))
        with patch.dict('os.environ',{},clear=True),patch('app.core.config.get_settings',return_value=configured):
            self.assertEqual(cipher().decrypt(cipher().encrypt(b'test')),b'test')
    async def test_admin_write_lock_rechecks_current_authority(self):
        from app.subscriptions.platform_management import lock_admin_management
        # Simulate authority having changed after request authentication but
        # before obtaining the serialized management lock.
        self.admin.active=False;await self.db.commit()
        with self.assertRaises(HTTPException) as error:await lock_admin_management(self.db,self.admin)
        self.assertEqual(error.exception.status_code,403)
    async def test_settings_version_trial_defaults_and_no_retroactive_changes(self):
        existing=await SubscriptionService(self.db).get_or_create_trial(self.company.id);end=existing.trial_ends_at
        async with await self.client() as client:
            current=(await client.get('/api/platform/settings')).json()
            payload={k:v for k,v in current.items() if k!='version'};payload.update(expected_version=current['version'],trial_days=14)
            response=await client.put('/api/platform/settings',json=payload);self.assertEqual(response.status_code,200,response.text)
            self.assertEqual((await client.put('/api/platform/settings',json=payload)).status_code,409)
            self.assertEqual((await SubscriptionService(self.db).get_or_create_trial(self.company.id)).trial_ends_at,end)
            from app.models import Company
            c=Company(name='Synthetic new trial',owner_email=str(uuid4())+'@trial.test');self.db.add(c);await self.db.commit()
            sub=await SubscriptionService(self.db).get_or_create_trial(c.id)
            self.assertAlmostEqual((sub.trial_ends_at-sub.trial_started_at).total_seconds(),14*86400)
    async def test_roles_and_tenant_tokens_cannot_manage_platform(self):
        for role in ('support','billing'):
            self.admin.role=role;await self.db.commit()
            async with await self.client() as client:
                for path in ('/api/platform/administrators','/api/platform/settings'):
                    response=await (client.post(path,json={'email':'x@y.test','password':'synthetic-long-password','role':'super_admin'}) if path.endswith('administrators') else client.put(path,json={'expected_version':0,'brand_name':'No','trial_days':30,'business_types':['Retail']}))
                    self.assertEqual(response.status_code,403,response.text)
                self.assertEqual((await client.get('/api/platform/administrators')).status_code,403)
        async with await self.client(create_access_token(str(self.user.id),self.user.email)) as client:
            self.assertEqual((await client.get('/api/platform/devices')).status_code,401)
    async def test_trial_extension_is_audited_idempotent_and_paid_accounts_reject(self):
        sub=await SubscriptionService(self.db).get_or_create_trial(self.company.id)
        end=sub.trial_ends_at
        async with await self.client() as client:
            payload={'expected_expiry':end.isoformat(),'expiry':(end+timedelta(days=5)).isoformat(),'reason':'Approved synthetic trial extension'}
            path=f'/api/platform/businesses/{self.company.id}/trial'
            first=await client.post(path,json=payload);self.assertEqual(first.status_code,200,first.text)
            retry=await client.post(path,json=payload);self.assertEqual(retry.status_code,200);self.assertFalse(retry.json()['changed'])
            self.assertEqual((await self.db.execute(select(func.count(PlatformAudit.id)).where(PlatformAudit.company_id==self.company.id,PlatformAudit.action=='platform_trial_extended'))).scalar_one(),1)
            sub.status='active';await self.db.commit()
            self.assertEqual((await client.post(path,json=payload)).status_code,409)
    async def test_admin_mutations_revoke_sessions_and_prevent_self_lockout(self):
        async with await self.client() as client:
            response=await client.post('/api/platform/administrators',json={'email':str(uuid4())+'@admin.test','password':'synthetic-admin-password','role':'support'})
            self.assertEqual(response.status_code,200,response.text);other=response.json()
            self.assertNotIn('password',response.text);self.assertFalse(other['mfa_enrolled'])
            self.assertEqual((await client.put(f'/api/platform/administrators/{self.admin.id}',json={'role':'support','active':False,'reason':'Self lockout blocked'})).status_code,409)
            other_row=(await self.db.execute(select(PlatformAdmin).where(PlatformAdmin.email==other['email']))).scalar_one()
            token=await self.token(other_row)
            response=await client.put(f"/api/platform/administrators/{other['id']}",json={'role':'billing','active':False,'reason':'Synthetic deactivation'})
            self.assertEqual(response.status_code,200,response.text)
            with self.assertRaises(HTTPException):await authenticate(self.db,token)
    async def test_sessions_are_scoped_and_recovery_does_not_reset_customer_credentials(self):
        async with await self.client() as client:
            response=await client.get('/api/platform/sessions');self.assertEqual(response.status_code,200);self.assertNotIn('token_hash',response.text)
            before=self.user.password_hash
            response=await client.post(f'/api/platform/businesses/{self.company.id}/recovery-review',json={'reason':'Verify original owner identity'})
            self.assertEqual(response.status_code,200);self.assertFalse(response.json()['account_changed']);self.assertEqual(self.user.password_hash,before)
            self.assertEqual((await client.get(f'/api/platform/devices/{self.device.id}/activity?company_id={uuid4()}')).status_code,404)
    async def test_device_reactivation_cannot_bypass_existing_claim(self):
        async with await self.client() as client:
            response=await client.post(f'/api/platform/devices/{self.device.id}/status?company_id={self.company.id}',json={'action':'activate','reason':'Synthetic attempt'})
            self.assertEqual(response.status_code,409)
            response=await client.post(f'/api/platform/devices/{self.device.id}/status?company_id={uuid4()}',json={'action':'revoke','reason':'Wrong company'})
            self.assertEqual(response.status_code,404)
    async def test_device_revocation_reuses_existing_lifecycle_and_preserves_stock(self):
        self.device.claimed_at=datetime.now(UTC);await self.db.commit()
        quantity=self.balance.quantity;sale_id=self.sale.id
        async with await self.client() as client:
            path=f'/api/platform/devices/{self.device.id}/status?company_id={self.company.id}'
            self.assertEqual((await client.post(path,json={'action':'revoke','reason':'Synthetic retirement'})).status_code,409)
            response=await client.post(path,json={'action':'revoke','reason':'Synthetic retirement','offline_queue_resolved':True,'active_checkout_closed':True})
            self.assertEqual(response.status_code,200,response.text)
            await self.db.refresh(self.session);self.assertIsNotNone(self.session.revoked_at)
            self.assertFalse(self.device.active);self.assertEqual(self.device.status,'deactivated')
            self.assertEqual(self.balance.quantity,quantity)
            from app.models import Sale
            self.assertIsNotNone(await self.db.get(Sale,sale_id))
            self.assertEqual((await client.post(path,json={'action':'activate','reason':'Cannot resurrect authority'})).status_code,409)
    async def test_non_root_session_directory_excludes_other_administrators(self):
        first=await self.token()
        other=PlatformAdmin(email=str(uuid4())+'@support.test',password_hash=hash_password('synthetic-admin-password'),role='support')
        self.db.add(other);await self.db.commit();second=await self.token(other)
        async with await self.client(second) as client:
            rows=(await client.get('/api/platform/sessions')).json()
            self.assertTrue(rows);self.assertTrue(all(r['admin_id']==str(other.id) for r in rows))
            _,root_session=await authenticate(self.db,first)
            self.assertEqual((await client.post(f'/api/platform/sessions/{root_session.id}/revoke')).status_code,404)
    async def test_downgrade_refuses_enrolled_administrators(self):
        await self.token()
        import importlib.util
        from pathlib import Path
        path=Path(__file__).resolve().parents[1]/'migrations/versions/p10a_platform_management.py'
        spec=importlib.util.spec_from_file_location('phase10_migration',path);migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
        def check(session):
            with patch.object(migration.op,'get_bind',return_value=session.connection()):
                with self.assertRaisesRegex(RuntimeError,'forward recovery'):migration.downgrade()
        await self.db.run_sync(check)
    async def test_operator_mfa_recovery_revokes_sessions_and_challenges_without_tenant_changes(self):
        token=await self.token();await login(self.db,self.admin.email,'synthetic-admin-password')
        from scripts import recover_platform_mfa as recovery
        from contextlib import asynccontextmanager
        @asynccontextmanager
        async def local_db():yield self.db
        password=self.user.password_hash
        with patch.object(recovery,'SessionLocal',local_db),patch.object(recovery.sys,'argv',['recover_platform_mfa',self.admin.email]),patch('builtins.input',side_effect=['RESET PLATFORM MFA '+self.admin.email,'Synthetic verified owner identity']),patch.object(recovery.getpass,'getpass',return_value='synthetic-admin-password'):
            await recovery.main()
        self.assertIsNone(self.admin.mfa_secret);self.assertEqual(self.user.password_hash,password)
        with self.assertRaises(HTTPException):await authenticate(self.db,token)
        challenges=(await self.db.execute(select(PlatformChallenge).where(PlatformChallenge.admin_id==self.admin.id))).scalars().all()
        self.assertTrue(all(c.used_at for c in challenges))
    async def test_platform_audits_remain_database_immutable(self):
        token=await self.token()
        self.assertTrue(token)
        with self.assertRaises(DBAPIError):
            async with self.db.begin_nested():await self.db.execute(text('UPDATE platform_audit SET action=\'tampered\' WHERE admin_id=:id'),{'id':self.admin.id})
