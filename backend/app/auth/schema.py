from pydantic import BaseModel, EmailStr

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    confirm_password: str
    business_name: str
    business_type: str
    country: str
    phone: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
