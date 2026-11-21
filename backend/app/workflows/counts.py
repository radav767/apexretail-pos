from uuid import UUID,uuid4,uuid5,NAMESPACE_URL
from decimal import Decimal
from datetime import datetime,timezone
import hashlib
from fastapi import HTTPException
from sqlalchemy import select,text,or_,and_
from sqlalchemy.dialects.postgresql import insert
from app.models import (WorkflowRecord,Product,ProductVariant,InventoryBalance,VariantInventoryBalance,ProductBatch,BatchReturnHold,BatchReturnInspection,InventoryMovement,StockRevision,Category)
from app.inventory.service import InventoryService
from app.inventory.schema import StockTakeCreate
from app.inventory.stock_repository import BranchStockRepository
from app.business_operations.batch_stock import LotInventoryRepository
from app.subscriptions.write_policy import require_new_write
from .procurement import DimensionRepository
from .core import WorkflowService,atomic

class CountRepository(DimensionRepository):
    async def get_product_for_update(self,company,product):
        row=(await self.db.execute(select(Product).where(Product.id==product,Product.company_id==company).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
        if not row:raise HTTPException(409,'Count product no longer exists')
        return row
    async def get_variant(self,company,product,variant):
        if not variant:return None
        row=(await self.db.execute(select(ProductVariant).where(ProductVariant.id==variant,ProductVariant.product_id==product,ProductVariant.company_id==company).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
        if not row:raise HTTPException(409,'Count variant no longer exists')
        return row
class CountLotRepository(LotInventoryRepository):
    get_product_for_update=CountRepository.get_product_for_update
    get_variant=CountRepository.get_variant

class CountService(WorkflowService):
    async def catalog(self,company,branch,category=None,products=None):
        await self.branch(company,branch)
        if category and not (await self.db.execute(select(Category.id).where(Category.id==category,Category.company_id==company))).scalar_one_or_none():raise HTTPException(404,'Count category not found')
        concrete=select(InventoryBalance.product_id).where(InventoryBalance.company_id==company,InventoryBalance.branch_id==branch)
        variant_positions=select(VariantInventoryBalance.product_id).where(VariantInventoryBalance.company_id==company,VariantInventoryBalance.branch_id==branch)
        query=select(Product).where(Product.company_id==company,or_(and_(Product.track_inventory.is_(True),Product.active.is_(True),Product.deleted.is_(False)),Product.id.in_(concrete),Product.id.in_(variant_positions)))
        if category:query=query.where(Product.category_id==category)
        if products:query=query.where(Product.id.in_(products))
        goods=(await self.db.execute(query.order_by(Product.id).limit(5001).execution_options(populate_existing=True))).scalars().all()
        if len(goods)>5000:raise HTTPException(422,'Count scope exceeds 5000 products; choose a narrower scope')
        pids=[p.id for p in goods]
        base={r.product_id:r for r in (await self.db.execute(select(InventoryBalance).where(InventoryBalance.company_id==company,InventoryBalance.branch_id==branch,InventoryBalance.product_id.in_(pids)).execution_options(populate_existing=True))).scalars()}
        variants=(await self.db.execute(select(ProductVariant).where(ProductVariant.company_id==company,ProductVariant.product_id.in_(pids)).order_by(ProductVariant.id).limit(5001).execution_options(populate_existing=True))).scalars().all()
        vb={r.variant_id:r for r in (await self.db.execute(select(VariantInventoryBalance).where(VariantInventoryBalance.company_id==company,VariantInventoryBalance.branch_id==branch,VariantInventoryBalance.product_id.in_(pids)).execution_options(populate_existing=True))).scalars()}
        lots=(await self.db.execute(select(ProductBatch).where(ProductBatch.company_id==company,ProductBatch.branch_id==branch,ProductBatch.product_id.in_(pids)).order_by(ProductBatch.id).limit(5001).execution_options(populate_existing=True))).scalars().all()
        holds=(await self.db.execute(select(BatchReturnHold,InventoryMovement.variant_id).join(InventoryMovement,InventoryMovement.id==BatchReturnHold.movement_id).outerjoin(BatchReturnInspection,BatchReturnInspection.hold_id==BatchReturnHold.id).where(BatchReturnHold.company_id==company,BatchReturnHold.branch_id==branch,BatchReturnInspection.id.is_(None),BatchReturnHold.product_id.in_(pids)).limit(5001))).all()
        known_base=set((await self.db.execute(select(InventoryBalance.product_id).where(InventoryBalance.company_id==company,InventoryBalance.product_id.in_(pids)).distinct())).scalars())
        known_variant=set((await self.db.execute(select(VariantInventoryBalance.product_id).where(VariantInventoryBalance.company_id==company,VariantInventoryBalance.product_id.in_(pids)).distinct())).scalars())
        if max(len(variants),len(vb),len(lots),len(holds))>5000:raise HTTPException(422,'Count dimensions exceed 5000 positions; narrow the scope')
        rows=[]
        for p in goods:
            if not p.track_inventory and not any(r.product_id==p.id and r.quantity for r in [*base.values(),*vb.values()]):continue
            vs=[v for v in variants if v.product_id==p.id]
            positions=[]
            if p.id in base and (base[p.id].quantity or not vs) or not vs and p.active and not p.deleted:positions.append((None,base.get(p.id),p.name))
            for v in vs:
                if v.id in vb or v.active and not v.deleted:positions.append((v.id,vb.get(v.id),p.name+' — '+v.name))
            for variant,balance,name in positions:
                qty=Decimal(balance.quantity if balance else 0)
                tracked=[lot for lot in lots if lot.product_id==p.id and lot.variant_id==variant]
                pending=[hold for hold,vid in holds if hold.product_id==p.id and vid==variant]
                orphan=balance is None and p.id not in known_base and p.id not in known_variant and Decimal(p.stock_qty or 0)>0
                blocked=orphan or not p.track_inventory or p.product_type in {'service','non_stock','composite','bundle'} or qty<0 or balance is not None and (not balance.active or balance.deleted)
                common={'product_id':str(p.id),'variant_id':str(variant) if variant else None,'name':name,'unit':p.unit,'measured':None,'blocked':bool(blocked)}
                if tracked or pending:
                    for lot in tracked:rows.append({**common,'key':'lot:'+str(lot.id),'kind':'lot','batch_id':str(lot.id),'lot_code':lot.code,'expires_on':str(lot.expires_on),'baseline':str(lot.quantity)})
                    for hold in pending:rows.append({**common,'key':'hold:'+str(hold.id),'kind':'hold','baseline':str(hold.quantity),'read_only':True})
                    unassigned=qty-sum((lot.quantity for lot in tracked),Decimal(0))-sum((hold.quantity for hold in pending),Decimal(0))
                    rows.append({**common,'key':f'unassigned:{p.id}:{variant or "base"}','kind':'unassigned','baseline':str(unassigned) if unassigned>=0 else None,'blocked':bool(blocked or unassigned<0),'read_only':True})
                else:rows.append({**common,'key':f'position:{p.id}:{variant or "base"}','kind':'position','baseline':None if orphan else str(qty)})
        if not rows or len(rows)>5000:raise HTTPException(422,'Count scope is empty or exceeds 5000 positions; select a narrower scope')
        if products and {r['product_id'] for r in rows}!={str(value) for value in products}:raise HTTPException(422,'Partial count contains an unknown/nonphysical product')
        return sorted(rows,key=lambda r:r['key'])
    async def baseline(self,data):
        if data.scope=='partial' and not data.product_ids or data.scope=='full' and data.product_ids:raise HTTPException(422,'Partial counts need explicit products; full counts use branch/category scope')
        rows=await self.catalog(data.company_id,data.branch_id,data.category_id,data.product_ids)
        keys=sorted({UUID(row['product_id']) for row in rows},key=str)
        revisions={}
        for product in keys:
            await self.db.execute(insert(StockRevision).values(company_id=data.company_id,branch_id=data.branch_id,product_id=product,revision=0).on_conflict_do_nothing())
            revisions[str(product)]=(await self.db.execute(select(StockRevision.revision).where(StockRevision.company_id==data.company_id,StockRevision.branch_id==data.branch_id,StockRevision.product_id==product))).scalar_one()
        return {'scope':data.scope,'category_id':str(data.category_id) if data.category_id else None,'product_ids':[str(i) for i in data.product_ids],'rows':rows,'revisions':revisions,'opened_at':datetime.now(timezone.utc).isoformat()}
    @atomic
    async def create_count(self,data):
        self.authorize(data.company_id,'inventory_count');await self.branch(data.company_id,data.branch_id)
        old,proof=await self.begin(data,'count_create',data.branch_id)
        if old:return old
        row=WorkflowRecord(id=uuid4(),company_id=data.company_id,branch_id=data.branch_id,kind='count',state='draft',payload=await self.baseline(data))
        self.db.add(row);return await self.finish(data,'count_create',row,proof)
    @atomic
    async def measure(self,count_id,data):
        self.authorize(data.company_id,'inventory_count')
        old,proof=await self.begin(data,'count_measure',record_id=count_id)
        if old:return old
        row=await self.record(data.company_id,count_id,'count',True);await self.check_scope(row)
        self.version(row,data,{'draft','counting'})
        if len({m.key for m in data.measurements})!=len(data.measurements):raise HTTPException(422,'Duplicate count measurement')
        entries={m.key:m.quantity for m in data.measurements};keys={r['key'] for r in row.payload['rows']}
        if not set(entries)<=keys:raise HTTPException(422,'Measured position is outside the frozen scope')
        payload={**row.payload,'rows':[{**r,'measured':str(entries[r['key']]) if r['key'] in entries else r['measured']} for r in row.payload['rows']]}
        row.payload=payload;row.state='counting';row.version+=1;return await self.finish(data,'count_measure',row,proof)
    async def check_scope(self,row):
        from app.inventory.command_policy import context
        await context(self.db,self.actor,row.company_id,row.branch_id)
    @atomic
    async def submit(self,count_id,data):
        self.authorize(data.company_id,'inventory_count')
        old,proof=await self.begin(data,'count_submit',record_id=count_id)
        if old:return old
        row=await self.record(data.company_id,count_id,'count',True);await self.check_scope(row);self.version(row,data,{'draft','counting'})
        if any(r['measured'] is None for r in row.payload['rows']):raise HTTPException(409,'Every frozen position needs an explicit count; missing is not zero')
        row.payload={**row.payload,'rows':[{**r,'variance':str(Decimal(r['measured'])-Decimal(r['baseline'])) if r['baseline'] is not None else 'Unavailable'} for r in row.payload['rows']]}
        row.state='submitted';row.version+=1;return await self.finish(data,'count_submit',row,proof)
    @atomic
    async def recount(self,count_id,data):
        self.authorize(data.company_id,'inventory_count')
        old,proof=await self.begin(data,'count_recount',record_id=count_id)
        if old:return old
        row=await self.record(data.company_id,count_id,'count',True);await self.check_scope(row);self.version(row,data,{'draft','counting','submitted','rejected'})
        if not data.reason.strip():raise HTTPException(422,'Recount reason is required')
        from .schema import CountInput
        previous=row.payload
        row.payload=await self.baseline(CountInput(company_id=data.company_id,request_id=data.request_id,branch_id=row.branch_id,scope=previous['scope'],category_id=previous['category_id'],product_ids=previous['product_ids']))
        row.state='draft';row.version+=1
        return await self.finish(data,'count_recount',row,proof,{**self.view(row),'previous_baseline':previous,'recount_reason':data.reason})
    @atomic
    async def reject_count(self,count_id,data):
        self.authorize(data.company_id,'inventory_count',owner=True)
        old,proof=await self.begin(data,'count_reject',record_id=count_id)
        if old:return old
        row=await self.record(data.company_id,count_id,'count',True);await self.check_scope(row);self.version(row,data,{'submitted'})
        if not data.reason.strip():raise HTTPException(422,'Variance rejection reason is required')
        row.state='rejected';row.version+=1
        return await self.finish(data,'count_reject',row,proof,{**self.view(row),'review_reason':data.reason})
    @atomic
    async def approve_count(self,count_id,data):
        self.authorize(data.company_id,'inventory_count',owner=True)
        old,proof=await self.begin(data,'count_approve',record_id=count_id)
        if old:return old
        row=await self.record(data.company_id,count_id,'count',True);await self.check_scope(row);self.version(row,data,{'submitted'})
        if not data.reason.strip():raise HTTPException(422,'Variance review reason is required')
        entries=row.payload['rows'];features=set()
        if any(e['variant_id'] for e in entries):features.add('variants')
        if any(e['kind']=='lot' for e in entries):features.add('pharmacy')
        await require_new_write(self.db,data.company_id,features=features)
        child={e['key']:uuid5(NAMESPACE_URL,f'phase11-count-session:{row.id}:{data.request_id}:{e["key"]}') for e in entries}
        # Existing immediate counts lock command before products. Reserve child
        # IDs in that same order before taking the position/cutoff locks.
        for request in sorted(child.values(),key=str):
            key=int.from_bytes(hashlib.sha256(f'count:{row.company_id}:{request}'.encode()).digest()[:8],'big',signed=True)
            await self.db.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':key})
        pids=sorted({UUID(e['product_id']) for e in entries},key=str)
        await self.db.execute(select(Product).where(Product.company_id==row.company_id,Product.id.in_(pids)).order_by(Product.id).with_for_update().execution_options(populate_existing=True))
        if set(row.payload['revisions'])!={str(value) for value in pids}:raise HTTPException(409,'Count cutoff proof requires an explicit recount')
        for product,revision in sorted(row.payload['revisions'].items()):
            live=(await self.db.execute(select(StockRevision.revision).where(StockRevision.company_id==row.company_id,StockRevision.branch_id==row.branch_id,StockRevision.product_id==UUID(product)).with_for_update())).scalar_one_or_none()
            if live!=revision:raise HTTPException(409,'Stock movement cutoff changed; retain this count and explicitly recount')
        current=await self.catalog(row.company_id,row.branch_id,UUID(row.payload['category_id']) if row.payload['category_id'] else None,[UUID(p) for p in row.payload['product_ids']])
        signature=lambda rows:[{key:value for key,value in r.items() if key not in {'measured','variance'}} for r in rows]
        if signature(current)!=signature(entries):raise HTTPException(409,'Physical count scope or baseline changed; explicitly recount')
        if any(e['measured'] is None or e['blocked'] or e.get('read_only') and Decimal(e['measured'])!=Decimal(e['baseline']) for e in entries):raise HTTPException(409,'Missing/blocked/held or unassigned discrepancy requires reviewed correction and recount')
        movements=[]
        for entry in sorted(entries,key=lambda r:(r['product_id'],r['variant_id'] or '',r['key'])):
            if entry.get('read_only') or Decimal(entry['measured'])==Decimal(entry['baseline']):continue
            p=UUID(entry['product_id']);v=UUID(entry['variant_id']) if entry['variant_id'] else None
            batch=await self.db.get(ProductBatch,UUID(entry['batch_id']),with_for_update=True,populate_existing=True) if entry['kind']=='lot' else None
            repo=CountLotRepository(self.db,batch) if batch else CountRepository(self.db)
            product=await repo.get_product_for_update(row.company_id,p)
            branch=await self.branch(row.company_id,row.branch_id)
            variant=await CountRepository(self.db).get_variant(row.company_id,p,v) if v else None
            balance=await repo.get_variant_balance(row.company_id,branch,product,variant) if v else await repo.get_balance_for_update(row.company_id,branch,product)
            before=Decimal(balance.quantity)
            physical=before+Decimal(entry['measured'])-Decimal(entry['baseline']) if batch else Decimal(entry['measured'])
            result=await InventoryService(repo).stock_take(StockTakeCreate(company_id=row.company_id,branch_id=row.branch_id,request_id=child[entry['key']],reference='COUNT-'+str(row.id),notes=data.reason,items=[{'product_id':p,'variant_id':v,'expected_qty':before if batch else Decimal(entry['baseline']),'physical_qty':physical}]),self.actor)
            movements.extend(str(m.id) for m in result)
        row.state='approved';row.version+=1
        return await self.finish(data,'count_approve',row,proof,{**self.view(row),'movement_ids':movements,'review_reason':data.reason})
