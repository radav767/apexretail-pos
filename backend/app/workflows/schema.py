from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import BaseModel,ConfigDict,Field,EmailStr

class Strict(BaseModel):model_config=ConfigDict(extra='forbid')
class Command(Strict):
    company_id:UUID
    request_id:UUID
class SupplierInput(Command):
    name:str=Field(min_length=1,max_length=160)
    contact:str=Field(default='',max_length=500)
class POLine(Strict):
    line_id:UUID
    product_id:UUID
    variant_id:UUID|None=None
    quantity:Decimal=Field(gt=0,max_digits=12,decimal_places=3)
    unit:str=Field(min_length=1,max_length=20)
    unit_cost:Decimal=Field(ge=0,max_digits=12,decimal_places=2)
class POInput(Command):
    branch_id:UUID
    supplier_id:UUID
    lines:list[POLine]=Field(min_length=1,max_length=100)
class VersionCommand(Command):
    version:int=Field(ge=1)
class ReceiveLine(Strict):
    line_id:UUID
    quantity:Decimal=Field(gt=0,max_digits=12,decimal_places=3)
    lot_code:str|None=Field(default=None,min_length=1,max_length=80)
    expires_on:date|None=None
class ReceiveInput(VersionCommand):
    lines:list[ReceiveLine]=Field(min_length=1,max_length=100)
    reference:str=Field(min_length=1,max_length=80)
class SupplierReturnInput(Command):
    receipt_id:UUID
    line_id:UUID
    quantity:Decimal=Field(gt=0,max_digits=12,decimal_places=3)
    reason:str=Field(min_length=1,max_length=160)

class CountInput(Command):
    branch_id:UUID
    scope:Literal['full','partial']='full'
    category_id:UUID|None=None
    product_ids:list[UUID]=Field(default_factory=list,max_length=1000)
class Measurement(Strict):
    key:str=Field(min_length=1,max_length=160)
    quantity:Decimal=Field(ge=0,max_digits=12,decimal_places=3)
class MeasureInput(VersionCommand):
    measurements:list[Measurement]=Field(min_length=1,max_length=5000)
class ReviewInput(VersionCommand):
    reason:str=Field(min_length=1,max_length=500)

class TemplateBlock(Strict):
    kind:Literal['title','text','terms','footer','contact']
    text:str=Field(min_length=1,max_length=2000)
class LogoBlock(Strict):
    kind:Literal['logo']
    media_id:UUID
    alignment:Literal['left','center','right']='center'
    width_mm:int=Field(default=30,ge=10,le=80)
class SourceBlock(Strict):
    kind:Literal['items','totals','tax']
class TemplateInput(Command):
    branch_id:UUID|None=None
    previous_id:UUID|None=None
    paper:Literal['58mm','80mm','A4']='80mm'
    blocks:list[TemplateBlock|LogoBlock|SourceBlock]=Field(min_length=1,max_length=20)
class DocumentInput(Command):
    template_id:UUID
    source_kind:Literal['sale','quotation','purchase_order','supplier_receipt','supplier_return','count_sheet']
    source_id:UUID

class PODraftUpdate(POInput):
    version:int=Field(ge=1)
class SupplierUpdate(VersionCommand):
    name:str=Field(min_length=1,max_length=160)
    contact:str=Field(default='',max_length=500)
    active:bool=True

class CancellationInput(Command):
    original_kind:str=Field(min_length=1,max_length=40)
    original_payload:dict
    record_id:UUID|None=None
    reason:str=Field(min_length=1,max_length=500)

class MediaInput(Command):
    branch_id:UUID|None=None
    content_type:Literal['image/png','image/jpeg','image/webp']
    data_base64:str=Field(min_length=4,max_length=699052)
class OutputInput(Command):
    document_id:UUID
    format:Literal['pdf','authenticated_lookup_qr']
class LookupInput(Strict):
    company_id:UUID
    document_id:UUID
    purpose:Literal['authenticated_document_lookup']
    content_digest:str=Field(pattern=r'^[0-9a-f]{64}$')
class ConsentInput(Command):
    branch_id:UUID|None=None
    recipient:EmailStr
    purpose:Literal['document_copy']
    confirmed:bool
class DeliveryInput(Command):
    output_id:UUID
    consent_id:UUID
class DeliveryAction(Command):
    reason:str=Field(min_length=1,max_length=500)
class MediaRetentionInput(Command):
    media_id:UUID
    archived:bool
    reason:str=Field(min_length=1,max_length=500)
