"""Read only the final synthetic shell tenant from its explicit private database."""
import asyncio,json,os
from pathlib import Path
from uuid import UUID
from sqlalchemy import select,func
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from app.models import Sale,InventoryBalance,InventoryMovement,QuotationCommand,CommerceOrder,SaleCommandReceipt,RefundCommandReceipt
url=make_url(os.environ['DATABASE_URL'])
assert os.environ['APP_ENV']=='test' and url.database=='apex_phase11_shell_20261121' and not url.host and url.query['host']=='/tmp/apex-phase11-postgres-auOybQ' and url.query['port']=='55441'
async def main():
    source=json.loads(Path('/tmp/phase11-quotation-shell-result.json').read_text());company=UUID(source['company']);product=UUID(source['product'])
    engine=create_async_engine(url);factory=async_sessionmaker(engine,expire_on_commit=False)
    async with factory() as db:
        originals=(await db.execute(select(Sale).where(Sale.company_id==company,Sale.original_sale_id.is_(None)))).scalars().all()
        refunds=(await db.execute(select(Sale).where(Sale.company_id==company,Sale.original_sale_id.is_not(None)))).scalars().all()
        assert len(originals)==2 and len(refunds)==2
        assert {r.id for r in originals}=={UUID(source['backoffice_sale']),UUID(source['pos_sale'])}
        assert sum(r.total_amount for r in originals)+sum(r.total_amount for r in refunds)==69
        assert sum(r.payment_amount_original for r in refunds)==-10353
        balance=(await db.execute(select(InventoryBalance.quantity).where(InventoryBalance.company_id==company,InventoryBalance.product_id==product))).scalar_one();assert balance==94
        async def count(model):return (await db.execute(select(func.count()).select_from(model).where(model.company_id==company))).scalar_one()
        assert await count(SaleCommandReceipt)==2 and await count(RefundCommandReceipt)==2 and await count(QuotationCommand)==10 and await count(CommerceOrder)==4
        movement_groups=(await db.execute(select(InventoryMovement.movement_type,func.count()).where(InventoryMovement.company_id==company,InventoryMovement.product_id==product).group_by(InventoryMovement.movement_type))).all()
        result={'synthetic_only':True,'company':str(company),'original_sales':2,'refund_sales':2,'sale_proofs':2,'refund_proofs':2,'quotation_commands':10,'quotation_orders':4,'stock':str(balance),'net_base_revenue':'69.00','refunded_original_JPY':'10353','movement_types':dict(movement_groups),'read_only_independent_connection':True}
        Path('/tmp/phase11-quotation-shell-persistence.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
    await engine.dispose()
asyncio.run(main())
