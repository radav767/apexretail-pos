from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from app.models import BusinessSession, BusinessRefreshCredential
from app.auth.remembered import COOKIE
from app.auth.security import hash_session_token
import test_phase11_user_sessions as session_fixtures


class RememberedSessionTests(session_fixtures.UserSessionTests):
    async def managed_login(self, remember=False):
        response = await self.client.post('/api/auth/login', headers={'Origin': 'https://backoffice.apexpos.cloud'}, json={
            'email': self.user.email, 'password': 'synthetic-session-password', 'client': 'backoffice', 'remember_me': remember})
        self.assertEqual(response.status_code, 200, response.text)
        return response

    async def refresh(self, secret):
        return await self.client.post('/api/auth/refresh', headers={'Origin': 'https://backoffice.apexpos.cloud', 'Cookie': f'{COOKIE}={secret}'})

    async def test_unchecked_cookie_is_session_only_and_remembered_is_bounded(self):
        normal = await self.managed_login()
        cookie = normal.headers['set-cookie']
        for flag in ('HttpOnly', 'Secure', 'SameSite=strict', 'Path=/'): self.assertIn(flag, cookie)
        self.assertNotIn('Max-Age', cookie)
        remembered = await self.managed_login(True)
        self.assertIn('Max-Age=', remembered.headers['set-cookie'])
        self.assertNotIn('refresh', remembered.json())
        session = (await self.db.execute(select(BusinessSession).where(BusinessSession.remembered.is_(True)))).scalar_one()
        self.assertLessEqual(session.expires_at - datetime.now(timezone.utc), timedelta(days=30))

    async def test_refresh_rotation_replay_revokes_family_and_issued_access(self):
        response = await self.managed_login(True)
        old = response.cookies[COOKIE]
        result = await self.refresh(old)
        self.assertEqual(result.status_code, 200, result.text)
        new = result.cookies[COOKIE]
        self.assertNotEqual(old, new)
        self.assertEqual((await self.read(result.json()['token'])).status_code, 200)
        credential = await self.db.get(BusinessRefreshCredential, hash_session_token(old))
        self.assertIsNotNone(credential.consumed_at)
        self.assertEqual((await self.refresh(old)).status_code, 401)
        self.assertEqual((await self.refresh(new)).status_code, 401)
        self.assertEqual((await self.read(result.json()['token'])).status_code, 401)

    async def test_current_logout_and_global_revocation_deny_access_and_refresh(self):
        response = await self.managed_login(True)
        token, secret = response.json()['token'], response.cookies[COOKIE]
        result = await self.client.post('/api/auth/logout', headers={**self.headers(token), 'Origin': 'https://backoffice.apexpos.cloud'})
        self.assertEqual(result.status_code, 200)
        self.assertEqual((await self.read(token)).status_code, 401)
        self.assertEqual((await self.refresh(secret)).status_code, 401)
        response = await self.managed_login(True)
        self.assertEqual((await self.logout(response.json()['token'])).status_code, 200)
        self.assertEqual((await self.refresh(response.cookies[COOKIE])).status_code, 401)

    async def test_refresh_origin_and_expired_session_fail_closed(self):
        response = await self.managed_login(True)
        secret = response.cookies[COOKIE]
        for origin in ('https://attacker.invalid', ''):
            result = await self.client.post('/api/auth/refresh', headers={'Origin': origin, 'Cookie': f'{COOKIE}={secret}'})
            self.assertEqual(result.status_code, 403)
        session = (await self.db.execute(select(BusinessSession))).scalar_one()
        session.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await self.db.commit()
        self.assertEqual((await self.refresh(secret)).status_code, 401)
        self.assertEqual((await self.read(response.json()['token'])).status_code, 401)
