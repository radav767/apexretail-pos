from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field, field_validator, model_validator

FEATURES=('restaurant','hospitality','pharmacy','wholesale','variants','composites','kitchen_printing','advanced_reports')

class PlanInput(BaseModel):
    name:str=Field(min_length=1,max_length=80)
    months:Literal[1,3,6,12]
    price:Decimal=Field(gt=0,max_digits=18,decimal_places=4)
    currency:str=Field(pattern=r'^[A-Z]{3,8}$')
    decimal_places:int=Field(default=2,ge=0,le=4)
    features:dict[str,bool]=Field(default_factory=dict)
    branch_limit:int|None=Field(default=None,ge=1)
    device_limit:int|None=Field(default=None,ge=1)
    employee_limit:int|None=Field(default=None,ge=1)
    offline_grace_hours:int=Field(default=72,ge=1,le=72)
    active:bool=True
    expected_version:int|None=Field(default=None,ge=1)

    @model_validator(mode='after')
    def valid_terms(self):
        if set(self.features)-set(FEATURES):raise ValueError('Unknown subscription feature')
        if self.price!=self.price.quantize(Decimal(1).scaleb(-self.decimal_places)):raise ValueError('Price exceeds currency precision')
        if not self.name.strip():raise ValueError('Plan name required')
        return self

class InvoiceInput(BaseModel):
    company_id:UUID
    plan_id:UUID
    request_id:UUID
    due_at:datetime
    custom_amount:Decimal|None=Field(default=None,gt=0,max_digits=18,decimal_places=4)
    reason:str=Field(min_length=3,max_length=500)
    @field_validator('due_at')
    @classmethod
    def aware(cls,value):
        if value.tzinfo is None:raise ValueError('Timezone required')
        return value

class PaymentInput(BaseModel):
    company_id:UUID
    invoice_id:UUID
    request_id:UUID
    amount:Decimal=Field(gt=0,max_digits=18,decimal_places=4)
    method:Literal['cash','card','mobile','bank']
    reference:str=Field(min_length=3,max_length=160)
    reason:str=Field(min_length=3,max_length=500)

class LicenseInput(BaseModel):
    action:Literal['suspend','reactivate']
    reason:str=Field(min_length=3,max_length=500)

class PlatformLogin(BaseModel):
    email:str=Field(min_length=3,max_length=160)
    password:str=Field(min_length=1,max_length=72)
    @field_validator('password')
    @classmethod
    def bounded_password(cls,value):
        if len(value.encode())>72:raise ValueError('Password exceeds supported UTF-8 length')
        return value
