import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
from cryptography.fernet import Fernet
from sqlalchemy import select, func
from app.auth.recovery import drain_sink
from app.auth.remembered import COOKIE
from app.auth.security import create_access_token, hash_session_token
from app.core.config import get_settings, Settings
from app.models import PasswordResetGrant, BusinessEmailOutbox
import test_phase11_user_sessions as fixtures


class PasswordRecoveryTests(fixtures.UserSessionTests):
    async def asyncSetUp(self):
        self.mode = patch.dict(os.environ, {'BUSINESS_EMAIL_MODE': 'sink', 'BUSINESS_EMAIL_KEY': Fernet.generate_key().decode()})
        self.mode.start(); get_settings.cache_clear()
        self.addCleanup(lambda: (self.mode.stop(), get_settings.cache_clear()))
        await super().asyncSetUp()
        self.sink = TemporaryDirectory(prefix='apex-phase11-email-sink-')
        self.addCleanup(self.sink.cleanup)

    async def request_reset(self, email=None):
        return await self.client.post('/api/auth/forgot-password', json={'email': email or self.user.email})

    async def tokens(self):
        paths = await drain_sink(self.db, self.sink.name)
        return [json.loads(Path(path).read_text())['reset_url'].split('#reset=')[1] for path in paths]

    async def reset(self, token):
        return await self.client.post('/api/auth/reset-password', json={'token': token,
            'password': 'new-synthetic-password', 'confirm_password': 'new-synthetic-password'})

    async def test_generic_request_encrypted_sink_and_durable_throttle(self):
        known = await self.request_reset()
        unknown = await self.request_reset('absent@example.com')
        self.assertEqual(known.status_code, 202); self.assertEqual(known.json(), unknown.json())
        row = (await self.db.execute(select(BusinessEmailOutbox))).scalar_one()
        self.assertNotIn(self.user.email.encode(), row.ciphertext)
        self.assertNotIn('token', known.text)
        for _ in range(4): self.assertEqual((await self.request_reset()).json(), known.json())
        self.assertEqual((await self.db.execute(select(func.count()).select_from(PasswordResetGrant))).scalar_one(), 3)
        tokens = await self.tokens()
        self.assertEqual(len(tokens), 3)
        self.assertEqual(await self.tokens(), [])
        for token in tokens:
            grant = await self.db.get(PasswordResetGrant, hash_session_token(token))
            self.assertNotEqual(grant.token_hash, token)
        self.assertEqual(row.ciphertext, b'')

    async def test_reset_consumes_once_invalidates_sibling_grants_access_and_refresh(self):
        legacy = create_access_token(str(self.user.id), self.user.email)
        login = await self.client.post('/api/auth/login', headers={'Origin': 'https://backoffice.apexpos.cloud'}, json={
            'email': self.user.email, 'password': 'synthetic-session-password', 'client': 'backoffice', 'remember_me': True})
        self.assertEqual(login.status_code, 200, login.text)
        await self.request_reset(); await self.request_reset()
        first, second = await self.tokens()
        self.assertEqual((await self.reset(first)).status_code, 200)
        self.assertEqual((await self.reset(first)).status_code, 400)
        self.assertEqual((await self.reset(second)).status_code, 400)
        for token in (legacy, login.json()['token']): self.assertEqual((await self.read(token)).status_code, 401)
        refreshed = await self.client.post('/api/auth/refresh', headers={'Origin': 'https://backoffice.apexpos.cloud', 'Cookie': f'{COOKIE}={login.cookies[COOKIE]}'})
        self.assertEqual(refreshed.status_code, 401)
        for password, expected in [('synthetic-session-password', 401), ('new-synthetic-password', 200)]:
            result = await self.client.post('/api/auth/login', json={'email': self.user.email, 'password': password})
            self.assertEqual(result.status_code, expected)

    async def test_expiry_disabled_user_and_password_validation(self):
        await self.request_reset(); token = (await self.tokens())[0]
        grant = await self.db.get(PasswordResetGrant, hash_session_token(token))
        grant.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1); await self.db.commit()
        self.assertEqual((await self.reset(token)).status_code, 400)
        await self.request_reset(); token = (await self.tokens())[0]
        self.user.active = False; await self.db.commit()
        self.assertEqual((await self.reset(token)).status_code, 400)
        result = await self.client.post('/api/auth/reset-password', json={'token': token, 'password': 'x' * 12, 'confirm_password': 'y' * 12})
        self.assertEqual(result.status_code, 422)
        self.assertEqual((await self.reset('x' * 43)).status_code, 400)

    async def test_sink_is_forbidden_in_production_configuration(self):
        with self.assertRaises(ValueError):
            Settings(database_url='postgresql://synthetic@localhost/unreachable', jwt_secret='synthetic-key-at-least-32-bytes-long',
                     app_env='production', business_email_mode='sink', business_email_key=Fernet.generate_key().decode(), _env_file=None)

    async def test_oversized_login_password_never_discloses_account_with_server_error(self):
        for email in (self.user.email, 'absent@example.com'):
            result = await self.client.post('/api/auth/login', json={'email': email, 'password': 'x' * 100})
            self.assertEqual(result.status_code, 401)
            self.assertEqual(result.json()['detail'], 'Invalid email or password')
