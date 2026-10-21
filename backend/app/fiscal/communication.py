"""Documented operation contract, independent of unverified HTTP route paths.

No production transport is provided. Exact HTTP method/path/binding comes from
the current official OpenAPI after review, not from guesses in this module.
"""
import ssl
from dataclasses import dataclass
from pathlib import Path
import stat
import re
from typing import Protocol
from uuid import UUID
from .adapter import FiscalIntegrationUnavailable

OPERATIONS = {'verifyTaxpayerInformation', 'registerDevice', 'issueCertificate', 'getConfig', 'getStatus',
              'openDay', 'submitReceipt', 'submitFile', 'getFileStatus', 'closeDay', 'getServerCertificate', 'ping'}


class FDMSOperationError(RuntimeError):
    """Sanitised HTTP problem, supplied by the future reviewed HTTP adapter."""
    def __init__(self, status: int, code: str):
        if status not in (400, 401, 404, 405, 422, 500, 502):
            raise ValueError('Unexpected FDMS status')
        self.status = status
        self.code = code if re.fullmatch('[A-Z0-9]{1,20}', code) else 'UNRECOGNISED'
        super().__init__(f'FDMS operation failed ({status}, {self.code})')


@dataclass(frozen=True)
class DeviceIdentity:
    company_id: str
    device_id: int
    model_name: str
    model_version: str
    environment: str


def client_tls_context(company_id, secret_directory, certificate_file, private_key_file, password=None):
    """Protected per-business provisioning only; never exposed via HTTP settings.

    HTTPS server validation uses system trust roots and hostname verification.
    Provisioning must separately validate FDMS issuer, CN, validity and key binding.
    """
    tenant = str(UUID(str(company_id)))
    root = Path(secret_directory).resolve(strict=True)
    base = root / tenant
    if base.is_symlink():
        raise FiscalIntegrationUnavailable('Credential directory must not be a symlink')
    base = base.resolve(strict=True)
    for directory in (root, base):
        metadata = directory.stat()
        if metadata.st_uid != 0 or not stat.S_ISDIR(metadata.st_mode) or metadata.st_mode & 0o022:
            raise FiscalIntegrationUnavailable('Credential directory must be protected')
    for raw in (certificate_file, private_key_file):
        file = Path(raw)
        if file.is_symlink() or file.resolve(strict=True).parent != base:
            raise FiscalIntegrationUnavailable('Credential path is not tenant-isolated')
        metadata = file.stat()
        if metadata.st_uid != 0 or not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077:
            raise FiscalIntegrationUnavailable('Credential files require protected root-only provisioning')
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(str(certificate_file), str(private_key_file), password=password)
    return context


class OperationTransport(Protocol):
    """A separately reviewed mTLS adapter must supply actual HTTP mapping."""
    async def request(self, operation: str, identity: DeviceIdentity, payload: dict,
                      headers: dict, timeout: float) -> dict: ...


class TestDeviceChannel:
    """Only explicitly injected test transports; never wired into public routes."""
    __test__ = False
    def __init__(self, identity: DeviceIdentity, transport: OperationTransport):
        if identity.environment != 'test':
            raise FiscalIntegrationUnavailable('Live fiscal communication is disabled')
        if not identity.model_name or not identity.model_version or identity.device_id <= 0:
            raise ValueError('Registered device identity required')
        self.identity, self.transport = identity, transport

    async def call(self, operation: str, payload: dict | None = None):
        if operation not in OPERATIONS:
            raise ValueError('Undocumented fiscal operation')
        headers = {'DeviceModelName': self.identity.model_name, 'DeviceModelVersionNo': self.identity.model_version}
        return await self.transport.request(operation, self.identity, payload or {}, headers, 30.0)
