from uuid import uuid4
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from app.models import Company, User, Branch, BackofficeHandoff, CompanySubscription
from app.auth.security import create_access_token, create_employee_access_token, hash_password, hash_session_token
from app.auth.remembered import COOKIE
import test_phase11_user_sessions as fixtures

ORIGIN = {'Origin': 'https://backoffice.apexpos.cloud'}


class HandoffTests(fixtures.UserSessionTests):
    async def issue(self, token=None, **changes):
        body = {'company_id': str(self.company.id), 'branch_id': str(self.branch.id)}; body.update(changes)
        return await self.client.post('/api/auth/handoff', headers=self.headers(token or create_access_token(str(self.user.id), self.user.email)), json=body)

    async def code(self, token=None):
        result = await self.issue(token)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertNotIn('?', result.json()['url'])
        return result.json()['url'].split('#handoff=')[1]

    async def inspect(self, code, receiver, cookie=None):
        headers = dict(ORIGIN)
        if cookie: headers['Cookie'] = f'{COOKIE}={cookie}'
        return await self.client.post('/api/auth/handoff/inspect', headers=headers, json={'code': code, 'receiver': receiver})

    async def consume(self, code, receiver, identity, **changes):
        body = {'code': code, 'receiver': receiver, 'company_id': identity['company_id'], 'branch_id': identity['branch_id'], 'role': identity['role']}
        body.update(changes)
        return await self.client.post('/api/auth/handoff/consume', headers=ORIGIN, json=body)

    async def test_two_accounts_replaces_previous_cookie_and_consumes_once(self):
        company = Company(name='Synthetic previous business', owner_email=f'{uuid4()}@example.com')
        self.db.add(company); await self.db.flush()
        previous = User(company_id=company.id, email=f'{uuid4()}@example.com', password_hash=hash_password('previous-synthetic-password'), role='owner')
        self.db.add(previous); await self.db.commit()
        old = await self.client.post('/api/auth/login', headers=ORIGIN, json={'email': previous.email, 'password': 'previous-synthetic-password', 'client': 'backoffice', 'remember_me': True})
        self.assertEqual(old.status_code, 200, old.text)
        code, receiver = await self.code(), str(uuid4())
        preview = await self.inspect(code, receiver, old.cookies[COOKIE])
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertEqual(preview.json()['email'], self.user.email)
        self.assertEqual((await self.read(old.json()['token'], company.id)).status_code, 401)
        consumed = await self.consume(code, receiver, preview.json())
        self.assertEqual(consumed.status_code, 200, consumed.text)
        self.assertEqual(consumed.json()['company_id'], str(self.company.id))
        self.assertEqual(consumed.json()['user']['id'], str(self.user.id))
        self.assertEqual((await self.read(consumed.json()['token'])).status_code, 200)
        self.assertEqual((await self.consume(code, receiver, preview.json())).status_code, 401)
        grant = await self.db.get(BackofficeHandoff, hash_session_token(code))
        self.assertIsNotNone(grant.consumed_at)
        self.assertNotEqual(code, grant.token_hash)

    async def test_cashier_wrong_tenant_branch_and_receiver_denied(self):
        employee = create_employee_access_token(employee_id=str(self.employee.id), company_id=str(self.company.id), role='owner')
        self.assertEqual((await self.issue(employee)).status_code, 403)
        self.assertEqual((await self.issue(company_id=str(uuid4()))).status_code, 403)
        self.assertEqual((await self.issue(branch_id=str(uuid4()))).status_code, 403)
        code, receiver = await self.code(), str(uuid4())
        preview = await self.inspect(code, receiver)
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertEqual((await self.inspect(code, str(uuid4()))).status_code, 401)
        self.assertEqual((await self.consume(code, str(uuid4()), preview.json())).status_code, 401)
        self.assertEqual((await self.consume(code, receiver, preview.json(), company_id=str(uuid4()))).status_code, 401)
        self.assertEqual((await self.consume(code, receiver, preview.json(), branch_id=str(uuid4()))).status_code, 401)
        self.assertEqual((await self.consume(code, receiver, preview.json(), role='administrator')).status_code, 401)

    async def test_expiry_role_change_global_logout_and_wrong_audience(self):
        for change in ('expired', 'role', 'version', 'audience'):
            code, receiver = await self.code(), str(uuid4())
            grant = await self.db.get(BackofficeHandoff, hash_session_token(code))
            if change == 'expired': grant.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            elif change == 'role': self.user.role = 'administrator'
            elif change == 'version': self.user.session_version += 1
            else: grant.audience = 'platform'
            await self.db.commit()
            self.assertEqual((await self.inspect(code, receiver)).status_code, 401, change)
            self.user.role = 'owner'
            # Mint subsequent test source credentials using the current version.
            if change == 'version':
                self.user.session_version = 0
            await self.db.commit()

    async def test_revoked_managed_source_and_untrusted_destination_origin_denied(self):
        source = await self.client.post('/api/auth/login', headers=ORIGIN, json={'email': self.user.email,
            'password': 'synthetic-session-password', 'client': 'backoffice'})
        code = await self.code(source.json()['token'])
        self.assertEqual((await self.client.post('/api/auth/logout', headers={**ORIGIN, **self.headers(source.json()['token'])})).status_code, 200)
        self.assertEqual((await self.inspect(code, str(uuid4()))).status_code, 401)
        result = await self.client.post('/api/auth/handoff/inspect', headers={'Origin': 'https://attacker.invalid'}, json={'code': code, 'receiver': str(uuid4())})
        self.assertEqual(result.status_code, 403)
        self.db.add(CompanySubscription(company_id=self.company.id, status='expired')); await self.db.commit()
        self.assertEqual((await self.issue()).status_code, 200)

    async def test_cashier_requires_fresh_same_business_owner_password(self):
        employee = create_employee_access_token(employee_id=str(self.employee.id), company_id=str(self.company.id), role='cashier')
        self.assertEqual((await self.issue(employee)).status_code, 403)
        self.assertEqual((await self.issue(employee, owner_email=self.user.email, owner_password='wrong-password')).status_code, 403)
        self.assertEqual((await self.issue(employee, owner_email=self.user.email, owner_password='synthetic-session-password', branch_id=str(uuid4()))).status_code, 403)
        foreign_company = Company(name='Synthetic foreign owner', owner_email=f'{uuid4()}@example.com')
        self.db.add(foreign_company); await self.db.flush()
        foreign_user = User(company_id=foreign_company.id, email=f'{uuid4()}@example.com',
                            password_hash=hash_password('foreign-synthetic-password'), role='owner')
        self.db.add(foreign_user); await self.db.commit()
        self.assertEqual((await self.issue(employee, owner_email=foreign_user.email, owner_password='foreign-synthetic-password')).status_code, 403)
        result = await self.issue(employee, owner_email=self.user.email, owner_password='synthetic-session-password')
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(set(result.json()), {'url'})
        code = result.json()['url'].split('#handoff=')[1]
        receiver = str(uuid4()); preview = await self.inspect(code, receiver)
        consumed = await self.consume(code, receiver, preview.json())
        self.assertEqual(consumed.status_code, 200, consumed.text)
        self.assertEqual(consumed.json()['user']['id'], str(self.user.id))

    async def test_owner_password_attempt_budget_is_not_reset_on_failure(self):
        employee = create_employee_access_token(employee_id=str(self.employee.id), company_id=str(self.company.id), role='cashier')
        for _ in range(5):
            self.assertEqual((await self.issue(employee, owner_email=self.user.email, owner_password='wrong-password')).status_code, 403)
        self.assertEqual((await self.issue(employee, owner_email=self.user.email, owner_password='synthetic-session-password')).status_code, 429)

    async def test_owner_proof_losing_revocation_race_does_not_invalidate_cashier(self):
        from app.auth.dependencies import resolve_auth_actor
        from app.auth.handoff import reauthenticate_owner, issue
        from app.auth.schema import HandoffCreate
        from fastapi import HTTPException
        employee = create_employee_access_token(employee_id=str(self.employee.id), company_id=str(self.company.id), role='cashier')
        actor = await resolve_auth_actor(employee, self.db)
        data = HandoffCreate(company_id=self.company.id, branch_id=self.branch.id,
                             owner_email=self.user.email, owner_password='synthetic-session-password')
        owner = await reauthenticate_owner(self.db, actor, data)
        self.user.session_version += 1; await self.db.commit()
        with self.assertRaises(HTTPException) as error:
            await issue(self.db, owner, self.company.id, self.branch.id)
        self.assertEqual(error.exception.status_code, 409)
        response = await self.client.get(f'/api/products/{self.company.id}', headers=self.headers(employee))
        self.assertEqual(response.status_code, 200)
