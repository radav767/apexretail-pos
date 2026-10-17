from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.auth.dependencies import AuthActor
from app.inventory.schema import GRNCreate
from app.inventory.service import InventoryService
from app.products.router import ensure_catalog_access
from app.products.schema import CategoryUpdate
from app.products.service import ProductService


class CategoryRepository:
    def __init__(self):
        self.company_id = uuid4()
        self.parent = SimpleNamespace(
            id=uuid4(), company_id=self.company_id, parent_id=None,
            name="Food", active=True, deleted=False, image_url=None,
        )
        self.child = SimpleNamespace(
            id=uuid4(), company_id=self.company_id, parent_id=self.parent.id,
            name="Prepared", active=True, deleted=False, image_url=None,
        )
        self.categories = {self.parent.id: self.parent, self.child.id: self.child}
        self.dependencies = (0, 0)

    async def get_category(self, company_id, category_id):
        category = self.categories.get(category_id)
        return category if category and category.company_id == company_id else None

    async def find_category_by_name(self, *_args, **_kwargs):
        return None

    async def category_dependency_counts(self, *_args):
        return self.dependencies

    async def delete_category(self, category):
        category.deleted = True

    async def update_category(self, category, changes):
        for key, value in changes.items():
            setattr(category, key, value)
        return category


@pytest.mark.asyncio
async def test_category_delete_is_blocked_when_products_depend_on_it():
    repo = CategoryRepository()
    repo.dependencies = (3, 0)
    service = ProductService(repo)
    with pytest.raises(HTTPException) as error:
        await service.delete_category(repo.company_id, repo.parent.id)
    assert error.value.status_code == 409
    assert repo.parent.deleted is False


@pytest.mark.asyncio
async def test_category_hierarchy_rejects_cycles():
    repo = CategoryRepository()
    service = ProductService(repo)
    with pytest.raises(HTTPException) as error:
        await service.update_category(
            repo.company_id,
            repo.parent.id,
            CategoryUpdate(parent_id=repo.child.id),
        )
    assert error.value.status_code == 400


class InventoryRepository:
    def __init__(self):
        self.branch = SimpleNamespace(id=uuid4(), shop_id=uuid4())
        self.product = SimpleNamespace(
            id=uuid4(), name="Water Bottle", unit="each", purchase_unit="carton",
            units_per_purchase=Decimal("24"), cost_price=Decimal("1"),
            reorder_level=Decimal("5"), stock_qty=Decimal("0"),
        )
        self.balance = SimpleNamespace(quantity=Decimal("10"))
        self.movement = None

    async def resolve_branch(self, *_args):
        return self.branch

    async def get_product_for_update(self, *_args):
        return self.product

    async def get_balance_for_update(self, *_args):
        return self.balance

    async def sync_product_total(self, *_args):
        return self.balance.quantity

    async def apply_movement(self, _product, _balance, movement):
        self.movement = movement
        return movement


@pytest.mark.asyncio
async def test_case_breaking_converts_purchase_units_to_base_stock():
    repo = InventoryRepository()
    service = InventoryService(repo)
    await service.receive_stock(
        GRNCreate(
            company_id=uuid4(), branch_id=repo.branch.id,
            product_id=repo.product.id, quantity=Decimal("2"),
            received_unit="carton", unit_cost=Decimal("24"),
            reason="Supplier delivery",
        )
    )
    assert repo.balance.quantity == Decimal("58.000")
    assert repo.movement.quantity == Decimal("48.000")
    assert repo.product.cost_price == Decimal("1.00")


def test_catalog_access_rejects_cross_company_actor():
    actor = AuthActor(actor_type="user", company_id=uuid4(), role="owner")
    with pytest.raises(HTTPException) as error:
        ensure_catalog_access(actor, uuid4())
    assert error.value.status_code == 403
