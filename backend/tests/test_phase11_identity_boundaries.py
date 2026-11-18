"""Direct API checks on rollback-only, synthetic PostgreSQL fixtures."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import unittest

from fastapi import Depends, FastAPI
import httpx
import jwt

from app.auth.dependencies import require_path_owner, require_path_permission
from app.auth.security import create_access_token, create_employee_access_token
from app.core.config import get_settings
from app.db.session import get_db
import test_phase7d_operations as fixtures


class IdentityBoundaryTests(unittest.IsolatedAsyncioTestCase):
    cleanup = fixtures.Phase7DOperationsTests.cleanup

    async def asyncSetUp(self):
        await fixtures.Phase7DOperationsTests.asyncSetUp(self)
        self.app = FastAPI()

        @self.app.get('/permission/{company_id}')
        async def permission(actor=Depends(require_path_permission('inventory_adjust'))):
            return {'company_id': str(actor.company_id)}

        @self.app.get('/owner/{company_id}')
        async def owner(actor=Depends(require_path_owner)):
            return {'company_id': str(actor.company_id)}

        async def override():
            yield self.db

        self.app.dependency_overrides[get_db] = override
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://isolated.test')
        self.addAsyncCleanup(self.client.aclose)

    async def request(self, kind, token, company=None):
        return await self.client.get(f'/{kind}/{company or self.company.id}',
                                     headers={'Authorization': 'Bearer ' + token})

    async def test_user_role_is_checked_on_every_request_and_tenant_gate_remains(self):
        token = create_access_token(str(self.user.id), self.user.email)
        for role in ('owner', 'administrator', 'accountant', 'cashier', 'unknown'):
            self.user.role = role
            await self.db.commit()
            with self.subTest(role=role):
                self.assertEqual((await self.request('permission', token)).status_code,
                                 200 if role in {'owner', 'administrator'} else 403)
                self.assertEqual((await self.request('owner', token)).status_code,
                                 200 if role == 'owner' else 403)
        self.user.role = 'owner'
        await self.db.commit()
        for kind in ('permission', 'owner'):
            self.assertEqual((await self.request(kind, token, uuid4())).status_code, 403)

    async def test_employee_permissions_remain_effective_without_owner_escalation(self):
        self.employee.permissions = {'inventory_adjust': False}
        await self.db.commit()
        token = create_employee_access_token(employee_id=str(self.employee.id),
                                            company_id=str(self.company.id), role='owner')
        # A stale signed role is never the source of current authorization.
        self.assertEqual((await self.request('permission', token)).status_code, 403)
        self.assertEqual((await self.request('owner', token)).status_code, 403)
        self.employee.permissions = {'inventory_adjust': True}
        await self.db.commit()
        self.assertEqual((await self.request('permission', token)).status_code, 200)
        self.assertEqual((await self.request('owner', token)).status_code, 403)
        self.assertEqual((await self.request('permission', token, uuid4())).status_code, 403)

    async def test_other_signed_token_purposes_never_become_user_sessions(self):
        settings = get_settings()
        claims = {'sub': str(self.user.id), 'exp': datetime.now(timezone.utc) + timedelta(minutes=5)}
        for token_type in ('offline_shift', 'entitlement', 'platform', 'handoff', 'reset', 'future-type',
                           '', None, False, 0, [], {}):
            token = jwt.encode({**claims, 'token_type': token_type}, settings.jwt_secret, algorithm=settings.jwt_algorithm)
            with self.subTest(token_type=token_type):
                self.assertEqual((await self.request('owner', token)).status_code, 401)
        legacy = jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)
        self.assertEqual((await self.request('owner', legacy)).status_code, 200)

    async def test_disabled_user_is_denied_with_previously_issued_token(self):
        token = create_access_token(str(self.user.id), self.user.email)
        self.user.active = False
        await self.db.commit()
        self.assertEqual((await self.request('owner', token)).status_code, 401)
