"""HTTP/DB acceptance on existing rollback-only fixtures, never live accounts."""
import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

from cryptography.fernet import Fernet
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.auth.security import create_access_token, hash_session_token
from app.models.commercial import PlatformAudit, PlatformSession
from app.subscriptions.platform_mfa import totp
import test_phase10_platform as fixtures

UTC = timezone.utc


class ReleaseAcceptance(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.PlatformTests.asyncSetUp
    cleanup = fixtures.PlatformTests.cleanup
    token = fixtures.PlatformTests.token
    client = fixtures.PlatformTests.client

    async def test_http_password_mfa_logout_and_secret_free_audit(self):
        async with await self.client('synthetic-invalid-not-a-session') as client:
            first = await client.post('/api/platform/login', json={
                'email': self.admin.email, 'password': 'synthetic-admin-password'})
            self.assertEqual(first.status_code, 200)
            challenge = first.json()
            self.assertNotIn('access_token', challenge)
            self.assertEqual((await client.get('/api/platform/dashboard')).status_code, 401)
            with patch('app.subscriptions.platform_mfa.time.time', return_value=self.now):
                second = await client.post('/api/platform/mfa', json={
                    'challenge': challenge['challenge'], 'code': totp(challenge['secret'], self.now // 30)})
            self.assertEqual(second.status_code, 200)
            token = second.json()['access_token']
            session = (await self.db.execute(select(PlatformSession).where(
                PlatformSession.token_hash == hash_session_token(token)))).scalar_one()
            self.assertTrue(session.mfa_verified)
            self.assertNotEqual(token, session.token_hash)
            self.assertLessEqual((session.expires_at - datetime.now(UTC)).total_seconds(), 1801)
            self.assertGreater(session.expires_at, datetime.now(UTC))
            client.headers['Authorization'] = 'Bearer ' + token
            self.assertEqual((await client.get('/api/platform/dashboard')).status_code, 200)
            self.assertEqual((await client.post('/api/platform/logout')).status_code, 200)
            self.assertEqual((await client.get('/api/platform/dashboard')).status_code, 401)
            await self.db.refresh(session)
            self.assertIsNotNone(session.revoked_at)
        audit = (await self.db.execute(select(PlatformAudit).where(
            PlatformAudit.admin_id == self.admin.id))).scalars().all()
        self.assertTrue({'platform_mfa_challenge', 'platform_login', 'platform_logout'} <= {a.action for a in audit})
        details = json.dumps([a.details for a in audit])
        for secret in (token, challenge['challenge'], challenge['secret'], 'synthetic-admin-password'):
            self.assertNotIn(secret, details)

    async def test_expired_revoked_and_disabled_sessions_rejected_over_http(self):
        token = await self.token()
        row = (await self.db.execute(select(PlatformSession).where(
            PlatformSession.token_hash == hash_session_token(token)))).scalar_one()
        async with await self.client(token) as client:
            row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await self.db.commit()
            self.assertEqual((await client.get('/api/platform/sessions')).status_code, 401)
            row.expires_at = datetime.now(UTC) + timedelta(minutes=10)
            row.revoked_at = datetime.now(UTC)
            await self.db.commit()
            self.assertEqual((await client.get('/api/platform/sessions')).status_code, 401)
            row.revoked_at = None
            self.admin.active = False
            await self.db.commit()
            self.assertEqual((await client.get('/api/platform/sessions')).status_code, 401)

    async def test_wrong_mfa_key_fails_closed_then_original_key_recovers(self):
        await self.token()
        password_before = self.user.password_hash
        self.now = 30 * (self.admin.mfa_last_step + 1)
        async with await self.client('synthetic-invalid-not-a-session') as client:
            first = await client.post('/api/platform/login', json={
                'email': self.admin.email, 'password': 'synthetic-admin-password'})
            self.assertEqual(first.status_code, 200)
            self.assertNotIn('secret', first.json())  # never disclose an enrolled factor
            payload = {'challenge': first.json()['challenge'], 'code': totp(self.secret, self.now // 30)}
            with patch.dict('os.environ', {'PLATFORM_MFA_KEY': Fernet.generate_key().decode()}), \
                 patch('app.subscriptions.platform_mfa.time.time', return_value=self.now):
                failed = await client.post('/api/platform/mfa', json=payload)
                self.assertEqual(failed.status_code, 503)
                self.assertNotIn('access_token', failed.json())
                self.assertNotIn(self.secret, failed.text)
            with patch('app.subscriptions.platform_mfa.time.time', return_value=self.now):
                recovered = await client.post('/api/platform/mfa', json=payload)
            self.assertEqual(recovered.status_code, 200)
        self.assertEqual(self.user.password_hash, password_before)

    async def test_runtime_role_cannot_update_or_delete_platform_audit(self):
        await self.token()
        privileges = (await self.db.execute(text("""SELECT
            has_table_privilege('apex_user','platform_audit','SELECT'),
            has_table_privilege('apex_user','platform_audit','INSERT'),
            has_table_privilege('apex_user','platform_audit','UPDATE'),
            has_table_privilege('apex_user','platform_audit','DELETE')"""))).one()
        self.assertEqual(tuple(privileges), (True, True, False, False))
        for statement in ('UPDATE platform_audit SET action=\'tampered\' WHERE admin_id=:id',
                          'DELETE FROM platform_audit WHERE admin_id=:id'):
            with self.subTest(statement=statement), self.assertRaises(DBAPIError):
                async with self.db.begin_nested():
                    await self.db.execute(text('SET LOCAL ROLE apex_user'))
                    await self.db.execute(text(statement), {'id': self.admin.id})
        self.assertEqual((await self.db.execute(text('SELECT current_user'))).scalar_one(), 'postgres')

    async def test_business_jwt_cannot_enter_platform_and_billing_stays_tenant_bound(self):
        business_token = create_access_token(str(self.user.id), self.user.email)
        async with await self.client(business_token) as client:
            for path in ('dashboard', 'businesses', 'plans', 'devices', 'fiscal', 'settings',
                         'administrators', 'sessions', 'health', 'audit'):
                with self.subTest(path=path):
                    self.assertEqual((await client.get('/api/platform/' + path)).status_code, 401)
            self.assertEqual((await client.get(f'/api/subscriptions/billing/{self.company.id}')).status_code, 200)
            self.assertEqual((await client.get(f'/api/subscriptions/billing/{uuid4()}')).status_code, 403)
