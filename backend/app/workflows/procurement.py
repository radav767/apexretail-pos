from uuid import UUID,uuid4
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select
from app.models import (WorkflowRecord,WorkflowCommand,Product,ProductVariant,ProductBatch,Company,CompanyCurrency)
from app.inventory.repository import InventoryRepository
from app.inventory.service import InventoryService
from app.inventory.schema import GRNCreate,StockAdjustmentCreate
from app.business_operations.batch_stock import LotInventoryRepository
from app.subscriptions.write_policy import require_new_write
from .core import WorkflowService,atomic

class DimensionRepository(InventoryRepository):
    def __init__(self,db,variant=None,returning=False):super().__init__(db,commit_on_save=False);self.variant=variant;self.returning=returning
    async def get_balance_for_update(self,company,branch,product):
        if self.variant:return await self.get_variant_balance(company,branch,product,self.variant)
        return await super().get_balance_for_update(company,branch,product)
    async def sync_product_total(self,product):
        if not self.variant:await super().sync_product_total(product)
    async def apply_movement(self,product,balance,movement):
        if self.variant:movement.variant_id=self.variant.id;movement.product_name=f'{product.name} — {self.variant.name}';movement.unit_cost=self.variant.cost_price or product.cost_price or 0
        if self.returning:movement.movement_type='supplier_return'
        return await super().apply_movement(product,balance,movement)

class ReturnLotRepository(LotInventoryRepository):
    async def apply_movement(self,product,balance,movement):
        movement.movement_type='supplier_return'
        return await super().apply_movement(product,balance,movement)

class ProcurementService(WorkflowService):
    @atomic
    async def supplier(self,data):
        self.authorize(data.company_id,owner=True)
        old,proof=await self.begin(data,'supplier_create')
        if old:return old
        if not data.name.strip():raise HTTPException(422,'Supplier name is required')
        row=WorkflowRecord(id=uuid4(),company_id=data.company_id,kind='supplier',state='active',payload={'name':data.name.strip(),'contact':data.contact.strip()})
        self.db.add(row);return await self.finish(data,'supplier_create',row,proof)
    @atomic
    async def update_supplier(self,supplier_id,data):
        self.authorize(data.company_id,owner=True)
        old,proof=await self.begin(data,'supplier_update',record_id=supplier_id)
        if old:return old
        row=await self.record(data.company_id,supplier_id,'supplier',True);self.version(row,data,{'active','inactive'})
        if not data.name.strip():raise HTTPException(422,'Supplier name is required')
        row.payload={'name':data.name.strip(),'contact':data.contact.strip()};row.state='active' if data.active else 'inactive';row.version+=1
        return await self.finish(data,'supplier_update',row,proof)
    @atomic
    async def edit_po(self,po_id,data):
        self.authorize(data.company_id,owner=True)
        old,proof=await self.begin(data,'po_edit',record_id=po_id)
        if old:return old
        row=await self.record(data.company_id,po_id,'po',True);self.version(row,data,{'draft'})
        if row.branch_id!=data.branch_id:raise HTTPException(409,'Draft branch is fixed; create a new draft to change location')
        await self.check_register(row.branch_id)
        supplier=await self.record(data.company_id,data.supplier_id,'supplier')
        if supplier.state!='active':raise HTTPException(409,'Supplier is inactive')
        row.payload={**row.payload,'supplier_id':str(supplier.id),'supplier_name':supplier.payload['name'],'lines':await self.freeze_lines(data)}
        row.version+=1;return await self.finish(data,'po_edit',row,proof)
    async def dimensions(self,company,lines,lock=False):
        ids=sorted({line.product_id for line in lines},key=str)
        query=select(Product).where(Product.company_id==company,Product.id.in_(ids)).order_by(Product.id)
        if lock:query=query.with_for_update()
        products={p.id:p for p in (await self.db.execute(query.execution_options(populate_existing=True))).scalars()}
        variants={}
        vids=sorted({line.variant_id for line in lines if line.variant_id},key=str)
        if vids:
            query=select(ProductVariant).where(ProductVariant.company_id==company,ProductVariant.id.in_(vids)).order_by(ProductVariant.id)
            if lock:query=query.with_for_update()
            variants={v.id:v for v in (await self.db.execute(query.execution_options(populate_existing=True))).scalars()}
        for line in lines:
            p=products.get(line.product_id);v=variants.get(line.variant_id)
            if not p or not p.active or p.deleted or not p.track_inventory or p.product_type in {'composite','bundle','service','non_stock'}:raise HTTPException(409,'PO line requires active physical stock')
            if line.variant_id and (not v or v.product_id!=p.id or not v.active or v.deleted):raise HTTPException(409,'Variant does not belong to the PO product')
            if not line.variant_id and (await self.db.execute(select(ProductVariant.id).where(ProductVariant.company_id==company,ProductVariant.product_id==p.id,ProductVariant.deleted.is_(False)).limit(1))).first():raise HTTPException(409,'Select the explicit product variant')
        return products,variants
    async def freeze_lines(self,data,lock=False):
        if len({line.line_id for line in data.lines})!=len(data.lines) or len({(line.product_id,line.variant_id) for line in data.lines})!=len(data.lines):raise HTTPException(422,'Duplicate PO line or stock position')
        products,variants=await self.dimensions(data.company_id,data.lines,lock)
        result=[]
        for line in data.lines:
            p=products[line.product_id];factor=Decimal(1)
            unit=line.unit.strip().lower()
            if unit!=p.unit:
                if unit!=str(p.purchase_unit or '').lower():raise HTTPException(422,'Unit does not match product base/purchase unit')
                factor=Decimal(p.units_per_purchase or 1)
            if factor<=0 or line.quantity*factor != (line.quantity*factor).quantize(Decimal('.001')):raise HTTPException(422,'Purchase conversion exceeds base stock precision')
            result.append({**line.model_dump(mode='json'),'unit':unit,'conversion':str(factor),'base_unit':p.unit,'name':p.name})
        return result
    @atomic
    async def create_po(self,data):
        self.authorize(data.company_id,owner=True);await self.branch(data.company_id,data.branch_id)
        old,proof=await self.begin(data,'po_create',data.branch_id)
        if old:return old
        supplier=await self.record(data.company_id,data.supplier_id,'supplier')
        if supplier.state!='active':raise HTTPException(409,'Supplier is inactive')
        lines=await self.freeze_lines(data)
        base=(await self.db.execute(select(CompanyCurrency).where(CompanyCurrency.company_id==data.company_id,CompanyCurrency.is_base.is_(True)))).scalar_one_or_none()
        if not base:raise HTTPException(409,'Base currency is not configured')
        row=WorkflowRecord(id=uuid4(),company_id=data.company_id,branch_id=data.branch_id,kind='po',state='draft',payload={'supplier_id':str(supplier.id),'supplier_name':supplier.payload['name'],'currency':base.code,'lines':lines})
        self.db.add(row);return await self.finish(data,'po_create',row,proof)
    @atomic
    async def approve(self,po_id,data):
        self.authorize(data.company_id,owner=True)
        old,proof=await self.begin(data,'po_approve',record_id=po_id)
        if old:return old
        row=await self.record(data.company_id,po_id,'po',True);await self.branch(data.company_id,row.branch_id)
        await self.check_register(row.branch_id)
        self.version(row,data,{'draft'})
        from .schema import POInput,POLine
        draft=POInput(company_id=data.company_id,request_id=data.request_id,branch_id=row.branch_id,supplier_id=UUID(row.payload['supplier_id']),lines=[POLine(**{k:v for k,v in line.items() if k not in {'conversion','base_unit','name'}}) for line in row.payload['lines']])
        if await self.freeze_lines(draft,True)!=row.payload['lines']:raise HTTPException(409,'Catalog/unit terms changed; create a revised draft')
        row.state='approved';row.version+=1;return await self.finish(data,'po_approve',row,proof)
    @atomic
    async def cancel_po(self,po_id,data):
        self.authorize(data.company_id,owner=True)
        old,proof=await self.begin(data,'po_cancel',record_id=po_id)
        if old:return old
        row=await self.record(data.company_id,po_id,'po',True);await self.check_register(row.branch_id)
        self.version(row,data,{'draft','approved','partially_received'})
        if not data.reason.strip():raise HTTPException(422,'Purchase cancellation reason is required')
        row.state='cancelled';row.version+=1
        return await self.finish(data,'po_cancel',row,proof,{**self.view(row),'review_reason':data.reason})
    async def check_register(self,branch):
        from app.inventory.command_policy import context
        await context(self.db,self.actor,self.actor.company_id,branch)
    async def receipts(self,row,kind='po_receive'):
        return (await self.db.execute(select(WorkflowCommand).where(WorkflowCommand.company_id==row.company_id,WorkflowCommand.record_id==row.id,WorkflowCommand.kind==kind))).scalars().all()
    @atomic
    async def receive(self,po_id,data):
        self.authorize(data.company_id,'inventory_receive');self.costs(data.company_id)
        old,proof=await self.begin(data,'po_receive',record_id=po_id)
        if old:return old
        row=await self.record(data.company_id,po_id,'po',True);await self.branch(data.company_id,row.branch_id);await self.check_register(row.branch_id)
        self.version(row,data,{'approved','partially_received'})
        planned={line['line_id']:line for line in row.payload['lines']}
        if len({line.line_id for line in data.lines})!=len(data.lines):raise HTTPException(422,'Duplicate receiving line')
        previous={key:Decimal(0) for key in planned}
        for receipt in await self.receipts(row):
            for line in receipt.result['lines']:previous[line['line_id']]+=Decimal(line['quantity'])
        from .schema import POLine
        targets=[]
        for entry in data.lines:
            line=planned.get(str(entry.line_id))
            if not line or previous[str(entry.line_id)]+entry.quantity>Decimal(line['quantity']):raise HTTPException(409,'Receipt exceeds remaining approved quantity or uses an unknown line')
            targets.append(POLine(**{k:v for k,v in line.items() if k not in {'conversion','base_unit','name'}}))
        products,variants=await self.dimensions(data.company_id,targets,True)
        if any(line.variant_id for line in targets):await require_new_write(self.db,data.company_id,features=('variants',))
        results=[]
        for entry in sorted(data.lines,key=lambda e:(planned[str(e.line_id)]['product_id'],planned[str(e.line_id)].get('variant_id') or '')):
            line=planned[str(entry.line_id)];p=products[UUID(line['product_id'])];v=variants.get(UUID(line['variant_id'])) if line['variant_id'] else None
            unit=line['unit'];factor=Decimal(line['conversion'])
            if p.unit!=line.get('base_unit'):raise HTTPException(409,'Original base-unit proof changed or requires review')
            if unit!=p.unit and (unit!=str(p.purchase_unit or '').lower() or factor!=Decimal(p.units_per_purchase or 1)):raise HTTPException(409,'Approved conversion changed; receipt needs review')
            if entry.quantity*factor!=(entry.quantity*factor).quantize(Decimal('.001')):raise HTTPException(422,'Receipt conversion exceeds stock precision')
            batch=None
            tracked=(await self.db.execute(select(ProductBatch.id).where(ProductBatch.company_id==data.company_id,ProductBatch.branch_id==row.branch_id,ProductBatch.product_id==p.id).limit(1))).first()
            company=await self.db.get(Company,data.company_id)
            from app.business_operations.profiles import infer_profile
            if entry.lot_code:
                if not entry.expires_on:raise HTTPException(422,'Lot expiry is required')
                await require_new_write(self.db,data.company_id,features=('pharmacy',))
                batch=(await self.db.execute(select(ProductBatch).where(ProductBatch.company_id==data.company_id,ProductBatch.branch_id==row.branch_id,ProductBatch.product_id==p.id,ProductBatch.variant_id==(v.id if v else None),ProductBatch.code==entry.lot_code).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
                if batch and batch.expires_on!=entry.expires_on:raise HTTPException(409,'Existing lot has a different expiry')
                if not batch:
                    batch=ProductBatch(company_id=data.company_id,branch_id=row.branch_id,product_id=p.id,variant_id=v.id if v else None,code=entry.lot_code,expires_on=entry.expires_on,quantity=0);self.db.add(batch);await self.db.flush()
            elif tracked or infer_profile(company.business_type)=='pharmacy' or entry.expires_on:raise HTTPException(409,'Receive this stock into an explicit lot and expiry')
            repo=LotInventoryRepository(self.db,batch) if batch else DimensionRepository(self.db,v)
            cost=Decimal(line['unit_cost'])
            if v:v.cost_price=(cost/factor).quantize(Decimal('.01'))
            movement=await InventoryService(repo).receive_stock(GRNCreate(company_id=data.company_id,branch_id=row.branch_id,product_id=p.id,quantity=entry.quantity,received_unit=unit if unit!=p.unit else None,unit_cost=None if v else cost,reference=data.reference,supplier=row.payload['supplier_name'],reason='Purchase order receiving'),self.actor)
            results.append({'line_id':str(entry.line_id),'quantity':str(entry.quantity),'base_quantity':str(entry.quantity*factor),'movement_id':str(movement.id),'batch_id':str(batch.id) if batch else None,'product_id':str(p.id),'variant_id':str(v.id) if v else None})
            previous[str(entry.line_id)]+=entry.quantity
        row.state='received' if all(previous[key]==Decimal(line['quantity']) for key,line in planned.items()) else 'partially_received';row.version+=1
        return await self.finish(data,'po_receive',row,proof,{'order':self.view(row),'lines':results,'reference':data.reference})
    @atomic
    async def supplier_return(self,po_id,data):
        self.authorize(data.company_id,'inventory_adjust');self.costs(data.company_id)
        old,proof=await self.begin(data,'supplier_return',record_id=po_id)
        if old:return old
        row=await self.record(data.company_id,po_id,'po',True);await self.branch(data.company_id,row.branch_id);await self.check_register(row.branch_id)
        receipt=await self.db.get(WorkflowCommand,data.receipt_id)
        if not receipt or receipt.company_id!=data.company_id or receipt.record_id!=row.id or receipt.kind!='po_receive':raise HTTPException(404,'Original supplier receipt not found')
        entry=next((line for line in receipt.result['lines'] if line['line_id']==str(data.line_id)),None)
        if not entry:raise HTTPException(404,'Original receipt line not found')
        returned=sum((Decimal(cmd.result['quantity']) for cmd in await self.receipts(row,'supplier_return') if cmd.result['receipt_id']==str(data.receipt_id) and cmd.result['line_id']==str(data.line_id)),Decimal(0))
        if returned+data.quantity>Decimal(entry['quantity']):raise HTTPException(409,'Supplier return exceeds unreturned receipt quantity')
        from .schema import POLine
        line=next(line for line in row.payload['lines'] if line['line_id']==str(data.line_id))
        products,variants=await self.dimensions(data.company_id,[POLine(**{k:v for k,v in line.items() if k not in {'conversion','base_unit','name'}})],True)
        p=products[UUID(line['product_id'])];v=variants.get(UUID(line['variant_id'])) if line['variant_id'] else None
        if v:await require_new_write(self.db,data.company_id,features=('variants',))
        batch=await self.db.get(ProductBatch,UUID(entry['batch_id']),with_for_update=True,populate_existing=True) if entry['batch_id'] else None
        if batch:
            await require_new_write(self.db,data.company_id,features=('pharmacy',))
            if batch.company_id!=data.company_id or batch.branch_id!=row.branch_id or batch.product_id!=p.id or batch.variant_id!=(v.id if v else None):raise HTTPException(409,'Original lot requires review')
        elif (await self.db.execute(select(ProductBatch.id).where(ProductBatch.company_id==data.company_id,ProductBatch.branch_id==row.branch_id,ProductBatch.product_id==p.id).limit(1))).first():raise HTTPException(409,'Original unassigned receipt requires reviewed lot attribution before return')
        amount=data.quantity*Decimal(line['conversion'])
        if p.unit!=line.get('base_unit') or amount!=amount.quantize(Decimal('.001')):raise HTTPException(409,'Original return unit/conversion requires review')
        if not data.reason.strip():raise HTTPException(422,'Supplier return reason is required')
        repo=ReturnLotRepository(self.db,batch) if batch else DimensionRepository(self.db,v,True)
        movement=await InventoryService(repo).adjust_stock(StockAdjustmentCreate(company_id=data.company_id,branch_id=row.branch_id,product_id=p.id,adjustment_type='remove',quantity=amount,reason=data.reason,reference='SUP-'+str(data.request_id)),self.actor)
        # Returns do not reopen the purchase budget or fabricate supplier payment.
        row.version+=1
        return await self.finish(data,'supplier_return',row,proof,{'order':self.view(row),'receipt_id':str(data.receipt_id),'line_id':str(data.line_id),'quantity':str(data.quantity),'movement_id':str(movement.id)})
