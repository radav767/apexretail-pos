"""Existing bootstrap CLI tested on rollback-only synthetic fixtures."""
import unittest
from contextlib import asynccontextmanager
from unittest.mock import patch
from uuid import uuid4
from sqlalchemy import select,func
from app.models.commercial import PlatformAdmin,PlatformAudit
from scripts import bootstrap_platform_admin as bootstrap
import test_phase7d_operations as fixtures

class InitialAdministrator(unittest.IsolatedAsyncioTestCase):
    cleanup=fixtures.Phase7DOperationsTests.cleanup
    async def asyncSetUp(self):await fixtures.Phase7DOperationsTests.asyncSetUp(self)
    async def invoke(self,email,password='synthetic-long-initial-password'):
        @asynccontextmanager
        async def local_db():yield self.db
        with patch.object(bootstrap,'SessionLocal',local_db),patch.object(bootstrap.sys,'argv',['bootstrap_platform_admin',email]),patch.object(bootstrap.getpass,'getpass',side_effect=[password,password]):
            await bootstrap.main()
    async def test_existing_cli_creates_only_audited_mfa_pending_platform_admin(self):
        email=str(uuid4())+'@platform.test';await self.invoke(email)
        row=(await self.db.execute(select(PlatformAdmin).where(PlatformAdmin.email==email))).scalar_one()
        self.assertEqual(row.role,'super_admin');self.assertTrue(row.active);self.assertIsNone(row.mfa_secret)
        self.assertEqual((await self.db.execute(select(func.count(PlatformAudit.id)).where(PlatformAudit.admin_id==row.id,PlatformAudit.action=='platform_admin_bootstrapped'))).scalar_one(),1)
        self.assertNotEqual(row.password_hash,'synthetic-long-initial-password')
        old=row.password_hash
        with self.assertRaisesRegex(SystemExit,'refusing overwrite'):await self.invoke(email)
        self.assertEqual(row.password_hash,old)
    async def test_invalid_password_cannot_create_platform_account(self):
        with self.assertRaisesRegex(SystemExit,'requirements'):await self.invoke(str(uuid4())+'@platform.test','short')
