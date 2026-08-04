from pydantic import BaseModel, EmailStr, Field


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


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
