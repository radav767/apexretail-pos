"""Explicit online split contract; legacy SaleCreate canonical shape is unchanged."""
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import BaseModel,ConfigDict,Field,model_validator,field_validator
from .schema import SaleCreate,SaleItemCreate
class TenderInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    id:UUID
    method:Literal['cash','credit']
    currency_code:str=Field(min_length=3,max_length=8)
    applied_original:Decimal=Field(gt=0,max_digits=18,decimal_places=4)
    tendered_original:Decimal|None=Field(default=None,ge=0,max_digits=18,decimal_places=4)
    applied_base:Decimal=Field(gt=0,max_digits=12,decimal_places=2)
    exchange_rate_id:UUID|None=None
    exchange_rate_snapshot:Decimal=Field(gt=0,max_digits=20,decimal_places=10)
    @field_validator('currency_code')
    @classmethod
    def code(cls,value):return value.strip().upper()
class SplitSaleCreate(SaleCreate):
    model_config=ConfigDict(extra='forbid')
    contract_version:Literal['split-v2']
    payment_method:Literal['split']='split'
    client_sale_id:UUID
    branch_id:UUID
    device_id:UUID
    assignment_revision:int=Field(ge=1)
    currency_config_version:int=Field(ge=1)
    expected_total:Decimal=Field(gt=0,max_digits=12,decimal_places=2)
    tenders:list[TenderInput]=Field(min_length=2,max_length=20)
    items:list[SaleItemCreate]=Field(min_length=1,max_length=100)
    @property
    def has_credit(self):return any(leg.method=='credit' for leg in self.tenders)
    @model_validator(mode='after')
    def online(self):
        if self.client_created_at is not None or self.offline_shift_token is not None:raise ValueError('Split checkout has no offline capture/lease authority')
        if any(value is not None for value in (self.amount_received,self.tendered_amount_original,self.payment_currency_code,self.exchange_rate_id,self.exchange_rate_snapshot)):raise ValueError('Split amounts/currencies belong to identified tender legs only')
        if len({leg.id for leg in self.tenders})!=len(self.tenders) or sum(leg.method=='credit' for leg in self.tenders)>1 or not any(leg.method=='cash' for leg in self.tenders):raise ValueError('Distinct legs, at most one credit leg and at least one cash leg are required')
        if any(leg.method=='credit' and leg.tendered_original not in (None,Decimal(0)) for leg in self.tenders):raise ValueError('A credit allocation is not received cash')
        return self
