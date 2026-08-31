from pydantic import BaseModel, EmailStr, Field, field_validator


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


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
