from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.auth.registration_currencies import REGISTRATION_CURRENCY_BY_CODE
from typing import Literal
from uuid import UUID


class RegisterRequest(BaseModel):
    owner_name: str = Field(min_length=2, max_length=120)
    owner_pin: str = Field(pattern=r"^\d{4}$")

    business_name: str = Field(min_length=2, max_length=160)
    business_type: str = Field(min_length=2, max_length=80)
    country: str = Field(min_length=2, max_length=100)
    phone: str = Field(min_length=3, max_length=40)

    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    confirm_password: str = Field(min_length=8, max_length=200)

    base_currency_code: str = Field(min_length=3, max_length=8)
    base_currency_symbol: str = Field(min_length=1, max_length=10)
    base_currency_decimal_places: int = Field(ge=0, le=2)

    # This connects the device created during registration
    # to the same browser that registered the business.
    device_key: str | None = Field(default=None, max_length=255)

    @field_validator(
        "owner_name",
        "business_name",
        "business_type",
        "country",
        "phone",
        mode="before",
    )
    @classmethod
    def strip_required_strings(cls, value: str):
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: str):
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("device_key", mode="before")
    @classmethod
    def normalize_device_key(cls, value: str | None):
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("base_currency_code", mode="before")
    @classmethod
    def normalize_currency_code(cls, value: str):
        if isinstance(value, str):
            return value.strip().upper()
        return value

    @field_validator("base_currency_symbol", mode="before")
    @classmethod
    def normalize_currency_symbol(cls, value: str):
        if isinstance(value, str):
            return value.strip()
        return value

    @model_validator(mode="after")
    def validate_supported_base_currency(self):
        if len(self.password.encode('utf-8')) > 72 or len(self.confirm_password.encode('utf-8')) > 72:
            raise ValueError('Passwords must use at most 72 UTF-8 bytes')
        definition = REGISTRATION_CURRENCY_BY_CODE.get(self.base_currency_code)
        if definition is None:
            raise ValueError("Select a supported base currency")
        if self.base_currency_symbol != definition.symbol:
            raise ValueError(
                f"The symbol for {definition.code} must be {definition.symbol}"
            )
        if self.base_currency_decimal_places != definition.decimal_places:
            raise ValueError(
                f"The decimal precision for {definition.code} must be "
                f"{definition.decimal_places}"
            )
        return self


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=200)
    client: Literal['pos', 'backoffice'] = 'pos'
    remember_me: bool = False


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=32, max_length=200)
    password: str = Field(min_length=12, max_length=72)
    confirm_password: str = Field(min_length=12, max_length=72)

    @model_validator(mode='after')
    def validate_password(self):
        if self.password != self.confirm_password or len(self.password.encode('utf-8')) > 72:
            raise ValueError('Passwords must match and use at most 72 UTF-8 bytes')
        return self


class HandoffCreate(BaseModel):
    company_id: UUID
    branch_id: UUID
    owner_email: EmailStr | None = None
    owner_password: str | None = Field(default=None, max_length=200)


class HandoffInspect(BaseModel):
    code: str = Field(min_length=32, max_length=200)
    receiver: str = Field(min_length=32, max_length=100)


class HandoffConsume(HandoffInspect):
    company_id: UUID
    branch_id: UUID
    role: Literal['owner', 'administrator']
