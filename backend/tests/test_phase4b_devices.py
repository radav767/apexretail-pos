import unittest
import json
from types import SimpleNamespace
from uuid import uuid4

from fastapi import HTTPException

from app.auth.security import hash_password
from app.devices.authority import TERMINAL_IDENTITY_REVOKED, hash_device_identity
from app.devices.schema import DeviceDeleteRequest, DeviceRegister
from app.devices.service import DeviceService
from app.employees.service import EmployeeService
from app.main import handle_http_exception


class FakeDB:
    def __init__(self):
        self.added = []
        self.committed = False
        self.rolled_back = False

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        return None

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


class LifecycleRepo:
    def __init__(self, device=None, *, active_sessions=0, deleted_identity=False):
        self.db = FakeDB()
        self.device = device
        self.tombstone = None
        self.active_sessions = active_sessions
        self.deleted_identity = deleted_identity
        self.revoked = False
        self.deleted = False

    async def get_by_id(self, company_id, device_id, *, for_update=False):
        if self.device and self.device.company_id == company_id and self.device.id == device_id:
            return self.device
        return None

    async def get_tombstone(self, company_id, device_id):
        if self.tombstone and self.tombstone.company_id == company_id and self.tombstone.id == device_id:
            return self.tombstone
        return None

    async def deletion_dependencies(self, device_id):
        return self.active_sessions, 7

    async def revoke_sessions(self, device_id, now, reason):
        self.revoked = True

    async def delete_activation_attempt(self, company_id, fingerprint):
        return None

    async def delete_device_row(self, device_id):
        self.tombstone = next(item for item in self.db.added if item.__class__.__name__ == "DeviceTombstone")
        self.device = None
        self.deleted = True

    async def identity_is_tombstoned(self, key_hash, fingerprint_hash=None):
        return self.deleted_identity


def device(company_id=None):
    company_id = company_id or uuid4()
    return SimpleNamespace(
        id=uuid4(), company_id=company_id, shop_id=uuid4(), branch_id=uuid4(),
        friendly_name="Front Counter", name="POS 1", pos_number=1,
        device_key="secret-device-key", device_fingerprint="fingerprint",
        activation_code_hash="activation-hash", activation_code_expires_at=None,
        assignment_revision=2, active=True, status="active", deleted=False,
        removed_at=None, deactivated_at=None, deactivation_reason=None,
        pending_shop_id=None, pending_branch_id=None,
    )


class Phase4BDeviceLifecycleTest(unittest.IsolatedAsyncioTestCase):
    def actor(self, company_id):
        return SimpleNamespace(
            actor_type="user", company_id=company_id,
            user=SimpleNamespace(id=uuid4(), password_hash=hash_password("correct-password")),
            employee=None,
        )

    async def test_delete_is_physical_idempotent_and_keeps_only_hashed_identity(self):
        target = device()
        repo = LifecycleRepo(target)
        service = DeviceService(repo)
        request = DeviceDeleteRequest(
            confirmation_name="Front Counter",
            reauthentication_secret="correct-password",
            reason="Synthetic test",
            offline_queue_resolved=True,
            active_checkout_closed=True,
        )
        first = await service.delete_permanently(target.company_id, target.id, request, self.actor(target.company_id))
        self.assertTrue(first["deleted"])
        self.assertFalse(first["already_deleted"])
        self.assertTrue(repo.revoked)
        self.assertTrue(repo.deleted)
        self.assertEqual(repo.tombstone.device_key_hash, hash_device_identity("secret-device-key"))
        self.assertNotIn("secret-device-key", repr(repo.tombstone.__dict__))
        second = await service.delete_permanently(target.company_id, target.id, request, self.actor(target.company_id))
        self.assertTrue(second["already_deleted"])

    async def test_delete_blocks_exact_active_dependency_and_bad_reauthentication(self):
        target = device()
        repo = LifecycleRepo(target, active_sessions=2)
        service = DeviceService(repo)
        with self.assertRaises(HTTPException) as auth_error:
            await service.delete_permanently(target.company_id, target.id, DeviceDeleteRequest(
                confirmation_name="Front Counter", reauthentication_secret="wrong", reason=None,
                offline_queue_resolved=True, active_checkout_closed=True,
            ), self.actor(target.company_id))
        self.assertEqual(auth_error.exception.status_code, 401)
        with self.assertRaisesRegex(HTTPException, "2 active POS session"):
            await service.delete_permanently(target.company_id, target.id, DeviceDeleteRequest(
                confirmation_name="Front Counter", reauthentication_secret="correct-password", reason=None,
                offline_queue_resolved=True, active_checkout_closed=True,
            ), self.actor(target.company_id))
        self.assertFalse(repo.deleted)

    async def test_deleted_identity_cannot_register_again(self):
        company_id = uuid4()
        repo = LifecycleRepo(deleted_identity=True)
        service = DeviceService(repo)
        with self.assertRaises(HTTPException) as denied:
            await service.register(DeviceRegister(company_id=company_id, device_key="deleted", name="POS"))
        self.assertEqual(denied.exception.status_code, 403)
        self.assertEqual(denied.exception.detail["code"], TERMINAL_IDENTITY_REVOKED)

    async def test_delete_requires_exact_name_and_client_state_protection(self):
        target = device()
        service = DeviceService(LifecycleRepo(target))
        with self.assertRaises(HTTPException) as unresolved:
            await service.delete_permanently(
                target.company_id,
                target.id,
                DeviceDeleteRequest(
                    confirmation_name="Front Counter",
                    reauthentication_secret="correct-password",
                ),
                self.actor(target.company_id),
            )
        self.assertEqual(unresolved.exception.status_code, 409)

        with self.assertRaises(HTTPException) as mismatched:
            await service.delete_permanently(
                target.company_id,
                target.id,
                DeviceDeleteRequest(
                    confirmation_name="front counter",
                    reauthentication_secret="correct-password",
                    offline_queue_resolved=True,
                    active_checkout_closed=True,
                ),
                self.actor(target.company_id),
            )
        self.assertEqual(mismatched.exception.status_code, 400)

    def test_manage_devices_is_elevated_by_default(self):
        self.assertTrue(EmployeeService.build_permissions("owner", None)["manage_devices"])
        self.assertTrue(EmployeeService.build_permissions("administrator", None)["manage_devices"])
        self.assertFalse(EmployeeService.build_permissions("manager", None)["manage_devices"])
        self.assertFalse(EmployeeService.build_permissions("cashier", None)["manage_devices"])

    async def test_terminal_authority_code_survives_http_serialization(self):
        response = await handle_http_exception(
            None,
            HTTPException(
                403,
                {
                    "code": TERMINAL_IDENTITY_REVOKED,
                    "message": "Terminal identity was deleted",
                },
            ),
        )
        payload = json.loads(response.body)
        self.assertEqual(payload["code"], TERMINAL_IDENTITY_REVOKED)
        self.assertEqual(payload["detail"], "Terminal identity was deleted")


if __name__ == "__main__":
    unittest.main()
