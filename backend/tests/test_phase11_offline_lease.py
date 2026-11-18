"""Fresh nonce is signed only after current tenant authentication; synthetic RSA keys."""
from datetime import datetime, timezone
from uuid import uuid4
import unittest
from unittest.mock import patch
import httpx
from app.auth.security import create_access_token, decode_entitlement_token
from app.core.config import get_settings
from app.db.session import get_db
from app.main import app
from app.models import CompanySubscription
from sqlalchemy import select
import test_phase7d_operations as fixtures
import test_entitlement_key_rotation as keys


class OfflineLeaseApiTests(unittest.IsolatedAsyncioTestCase):
    cleanup = fixtures.Phase7DOperationsTests.cleanup
    _write_private = keys.EntitlementKeyRotationTest._write_private
    _write_keyring = keys.EntitlementKeyRotationTest._write_keyring
    settings = keys.EntitlementKeyRotationTest.settings

    async def asyncSetUp(self):
        await fixtures.Phase7DOperationsTests.asyncSetUp(self)
        keys.EntitlementKeyRotationTest.setUp(self)
        self.signing = self.settings()
        self.signing.jwt_secret = get_settings().jwt_secret
        self.signing.jwt_algorithm = get_settings().jwt_algorithm
        self.token = create_access_token(str(self.user.id), self.user.email)
        async def override(): yield self.db
        app.dependency_overrides[get_db] = override; self.addCleanup(app.dependency_overrides.clear)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://synthetic.test')
        self.addAsyncCleanup(self.client.aclose)

    async def page(self, nonce, token=None, company=None):
        return await self.client.get('/api/subscriptions/'+str(company or self.company.id),
            params={'lease_nonce':nonce}, headers={'Authorization':'Bearer '+(token or self.token)})

    async def test_signed_current_server_time_and_nonce_cannot_be_substituted(self):
        first,second=str(uuid4()),str(uuid4())
        with patch('app.auth.security.get_settings',return_value=self.signing):
            response=await self.page(first);self.assertEqual(response.status_code,200,response.text)
            claims=decode_entitlement_token(response.json()['current']['snapshot']['snapshot_token'],expected_company_id=str(self.company.id))
            self.assertEqual(claims['lease_nonce'],first)
            self.assertLess(abs(claims['iat']-datetime.now(timezone.utc).timestamp()),5)
            response=await self.page(second);self.assertEqual(response.status_code,200,response.text)
            next_claims=decode_entitlement_token(response.json()['current']['snapshot']['snapshot_token'],expected_company_id=str(self.company.id))
            self.assertEqual(next_claims['lease_nonce'],second);self.assertNotEqual(first,second)
            self.assertEqual((await self.page(first,company=uuid4())).status_code,403)
            self.assertEqual((await self.page('unsafe')).status_code,422)

    async def test_suspension_is_signed_non_writable_and_revoked_actor_cannot_renew(self):
        subscription=(await self.db.execute(select(CompanySubscription).where(CompanySubscription.company_id==self.company.id))).scalar_one()
        subscription.status='suspended';await self.db.commit()
        with patch('app.auth.security.get_settings',return_value=self.signing):
            response=await self.page(str(uuid4()));self.assertEqual(response.status_code,200,response.text)
            snapshot=response.json()['current']['snapshot'];self.assertFalse(snapshot['writes_allowed'])
            # Signature is still real; verifier denies its non-writable status.
            from app.auth.security import EntitlementVerificationError
            with self.assertRaises(EntitlementVerificationError) as error:
                decode_entitlement_token(snapshot['snapshot_token'],expected_company_id=str(self.company.id))
            self.assertEqual(error.exception.category,'subscription_not_writable')
            self.user.session_version+=1;await self.db.commit()
            self.assertEqual((await self.page(str(uuid4()))).status_code,401)
