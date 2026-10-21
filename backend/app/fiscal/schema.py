from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator


class TaxMapping(BaseModel):
    model_config = ConfigDict(extra='forbid')
    local_code: str = Field(min_length=1, max_length=40, pattern=r'^[A-Za-z0-9_-]+$')
    tax_id: int = Field(gt=0)
    # None is exempt, zero is zero-rated. No default statutory rates.
    percent: Decimal | None = Field(default=None, ge=0, le=100, decimal_places=2)
    valid_from: datetime
    valid_till: datetime | None = None

    @model_validator(mode='after')
    def dates(self):
        if self.valid_from.tzinfo is None or (self.valid_till and self.valid_till.tzinfo is None):
            raise ValueError('Tax validity requires timezone-aware dates')
        if self.valid_till and self.valid_till < self.valid_from:
            raise ValueError('Invalid tax validity range')
        return self


class FiscalSettings(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    expected_version: int = Field(default=0, ge=0)
    environment: Literal['test', 'production'] = 'test'
    provider: Literal['zimra_fdms'] = 'zimra_fdms'
    taxpayer_tin: str = Field(pattern=r'^\d{10}$')
    vat_number: str | None = Field(default=None, pattern=r'^\d{9}$')
    branch_id: UUID
    register_id: UUID
    device_id: int = Field(gt=0, le=2147483647)
    device_serial: str = Field(min_length=1, max_length=20)
    model_name: str = Field(min_length=1, max_length=100)
    model_version: str = Field(min_length=1, max_length=50)
    # Opaque reference only, never activation keys, certificates or private keys.
    credential_reference: str | None = Field(default=None, max_length=160, pattern=r'^[a-zA-Z0-9/_-]+$')
    taxes: list[TaxMapping] = Field(default_factory=list, max_length=100)

    @model_validator(mode='after')
    def unique_taxes(self):
        if len({t.local_code for t in self.taxes}) != len(self.taxes):
            raise ValueError('Duplicate local tax codes')
        return self
