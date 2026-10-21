"""Adapter boundary; no guessed HTTP routes, no live network side effects."""
from typing import Protocol


class FiscalIntegrationUnavailable(RuntimeError):
    pass


class FiscalAdapter(Protocol):
    async def get_configuration(self, device_id: int) -> dict: ...
    async def get_status(self, device_id: int) -> dict: ...
    async def submit_receipt(self, device_id: int, signed_receipt: dict) -> dict: ...


class UncommissionedFDMSAdapter:
    """Fail closed until approved onboarding, transport and signing are verified.

    Deliberately no HTTP client and no environment-variable escape hatch.
    Registered test credentials and current OpenAPI are external release gates.
    """
    async def get_configuration(self, device_id: int) -> dict:
        raise FiscalIntegrationUnavailable('FDMS commissioning and test credentials required')

    async def get_status(self, device_id: int) -> dict:
        raise FiscalIntegrationUnavailable('FDMS commissioning and test credentials required')

    async def submit_receipt(self, device_id: int, signed_receipt: dict) -> dict:
        raise FiscalIntegrationUnavailable('Fiscal submission is disabled; no receipt was transmitted')
