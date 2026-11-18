"""Synthetic ASGI/session revocation tests on the private rollback fixture DB."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import unittest
from unittest.mock import patch

import httpx
import jwt
from sqlalchemy import select

from app.auth.security import create_access_token, create_employee_access_token, hash_password
from app.core.config import get_settings
from app.db.session import get_db
from app.main import app
from app.models import AuditEvent, Company, CompanySubscription, User
import test_phase7d_operations as fixtures


class UserSessionTests(unittest.IsolatedAsyncioTestCase):
    cleanup = fixtures.Phase7DOperationsTests.cleanup

    async def asyncSetUp(self):
        await fixtures.Phase7DOperationsTests.asyncSetUp(self)
        self.user.email = f'{uuid4()}@example.com'
        self.user.password_hash = hash_password('synthetic-session-password')
        await self.db.commit()

        async def override():
            yield self.db

        app.dependency_overrides[get_db] = override
        self.addCleanup(app.dependency_overrides.clear)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://isolated.test')
        self.addAsyncCleanup(self.client.aclose)

    def headers(self, token):
        return {'Authorization': 'Bearer ' + token}

    async def read(self, token, company=None):
        return await self.client.get(f'/api/fiscal/{company or self.company.id}/configuration', headers=self.headers(token))

    async def logout(self, token):
        return await self.client.post('/api/auth/logout-all', headers=self.headers(token))

    async def test_revokes_current_and_legacy_tokens_then_password_login_uses_new_version(self):
        current = create_access_token(str(self.user.id), self.user.email)
        settings = get_settings()
        legacy = jwt.encode({'sub': str(self.user.id), 'exp': datetime.now(timezone.utc) + timedelta(minutes=5)},
                            settings.jwt_secret, algorithm=settings.jwt_algorithm)
        for token in (current, legacy):
            self.assertEqual((await self.read(token)).status_code, 200)
        response = await self.logout(current)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'ok': True, 'scope': 'all_user_sessions'})
        for token in (current, legacy):
            self.assertEqual((await self.read(token)).status_code, 401)
            self.assertEqual((await self.logout(token)).status_code, 401)
        response = await self.client.post('/api/auth/login', json={'email': self.user.email, 'password': 'synthetic-session-password'})
        self.assertEqual(response.status_code, 200, response.text)
        fresh = response.json()['token']
        self.assertEqual(jwt.decode(fresh, settings.jwt_secret, algorithms=[settings.jwt_algorithm])['session_version'], 1)
        self.assertEqual((await self.read(fresh)).status_code, 200)
        audits = (await self.db.execute(select(AuditEvent).where(AuditEvent.company_id == self.company.id,
                  AuditEvent.action == 'business_user_sessions_revoked'))).scalars().all()
        self.assertEqual(len(audits), 1)
        self.assertEqual(audits[0].details, {'scope': 'all_user_sessions'})

    async def test_another_tenant_is_unaffected_and_employee_cannot_revoke_user(self):
        other_company = Company(name='Synthetic isolated second tenant', owner_email=f'{uuid4()}@example.com')
        self.db.add(other_company)
        await self.db.flush()
        other = User(company_id=other_company.id, email=f'{uuid4()}@example.com',
                     password_hash='not-used-for-login', role='owner')
        self.db.add(other)
        await self.db.commit()
        other_token = create_access_token(str(other.id), other.email)
        employee_token = create_employee_access_token(employee_id=str(self.employee.id),
                                                     company_id=str(self.company.id), role=self.employee.role)
        self.assertEqual((await self.logout(employee_token)).status_code, 403)
        self.assertEqual((await self.client.post('/api/auth/logout-all')).status_code, 401)
        self.assertEqual((await self.logout(create_access_token(str(self.user.id), self.user.email))).status_code, 200)
        self.assertEqual((await self.read(other_token, other_company.id)).status_code, 200)
        self.assertEqual((await self.read(other_token)).status_code, 403)

    async def test_expired_subscription_can_still_revoke_and_versions_are_strict(self):
        self.db.add(CompanySubscription(company_id=self.company.id, status='expired'))
        await self.db.commit()
        settings = get_settings()
        for value in (None, True, False, '0', -1, 0.0):
            token = jwt.encode({'sub': str(self.user.id), 'token_type': 'user', 'session_version': value,
                                'exp': datetime.now(timezone.utc) + timedelta(minutes=5)},
                               settings.jwt_secret, algorithm=settings.jwt_algorithm)
            with self.subTest(version=value):
                self.assertEqual((await self.logout(token)).status_code, 401)
        self.assertEqual((await self.logout(create_access_token(str(self.user.id), self.user.email))).status_code, 200)

    async def test_downgrade_refuses_to_restore_revoked_authority(self):
        from migrations.versions import p11a_user_session_revocation as migration
        await self.logout(create_access_token(str(self.user.id), self.user.email))

        def downgrade(connection):
            with patch.object(migration.op, 'get_bind', return_value=connection):
                migration.downgrade()

        connection = await self.db.connection()
        with self.assertRaisesRegex(RuntimeError, 'Revoked user sessions exist'):
            await connection.run_sync(downgrade)

    async def test_registration_issues_initial_version_without_requiring_provider_delivery(self):
        response = await self.client.post('/api/auth/register', json={
            'owner_name': 'Synthetic New Owner', 'owner_pin': '1234',
            'business_name': 'Synthetic New Business', 'business_type': 'Retail',
            'country': 'Zimbabwe', 'phone': '000000000', 'email': f'{uuid4()}@example.com',
            'password': 'synthetic-registration-password', 'confirm_password': 'synthetic-registration-password',
            'base_currency_code': 'USD', 'base_currency_symbol': '$', 'base_currency_decimal_places': 2,
            'device_key': str(uuid4()),
        })
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        settings = get_settings()
        self.assertEqual(jwt.decode(data['token'], settings.jwt_secret, algorithms=[settings.jwt_algorithm])['session_version'], 0)
        self.assertEqual((await self.read(data['token'], data['company']['id'])).status_code, 200)
