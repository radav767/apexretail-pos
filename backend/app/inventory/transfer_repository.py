from app.inventory.stock_repository import BranchStockRepository


class TransferRepository:
    def __init__(self, db):
        self.db = db
        self.stock = BranchStockRepository(db)

    async def resolve_branch(
        self,
        company_id,
        branch_id,
    ):
        return await self.stock.resolve_branch(
            company_id,
            branch_id,
        )

    async def get_product(
        self,
        company_id,
        product_id,
    ):
        return await self.stock.get_product_for_update(
            company_id,
            product_id,
        )

    async def get_balance(
        self,
        company_id,
        branch,
        product,
    ):
        return await self.stock.get_balance_for_update(
            company_id,
            branch,
            product,
        )

    async def sync_product_total(self, product):
        return await self.stock.sync_product_total(product)

    async def save_transfer(
        self,
        products,
        balances,
        movements,
    ):
        try:
            self.db.add_all(products)
            self.db.add_all(balances)
            self.db.add_all(movements)

            from app.business_operations.batches import allocate_batch_movements
            await allocate_batch_movements(self.db, movements)
            await self.db.commit()

            for movement in movements:
                await self.db.refresh(movement)

            return movements
        except Exception:
            await self.db.rollback()
            raise
