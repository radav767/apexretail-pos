"""Availability is public deployment metadata, never account existence."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import httpx
from app.main import app

class AuthCapabilitiesTests(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_production_and_test_sink_are_explicit_and_never_cached(self):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://synthetic.invalid') as client:
            for env,mode,expected in [('production','disabled','unavailable'),('test','disabled','unavailable'),('test','sink','test_sink')]:
                with self.subTest(env=env,mode=mode), patch('app.core.config.get_settings',return_value=SimpleNamespace(app_env=env,business_email_mode=mode)):
                    r=await client.get('/api/auth/capabilities')
                    self.assertEqual(r.status_code,200)
                    self.assertEqual(r.json(),{'password_recovery':expected})
                    self.assertEqual(r.headers['Cache-Control'],'no-store')
