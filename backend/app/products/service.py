from app.models.category import Category
from app.models.product import Product
from app.products.repository import ProductRepository
from app.products.schema import CategoryCreate, ProductCreate


class ProductService:
    def __init__(self, repo: ProductRepository):
        self.repo = repo

    async def create_category(self, data: CategoryCreate):
        category = Category(
            company_id=data.company_id,
            name=data.name.strip(),
        )
        return await self.repo.create_category(category)

    async def list_categories(self, company_id):
        return await self.repo.list_categories(company_id)

    async def create_product(self, data: ProductCreate):
        product = Product(**data.model_dump())
        return await self.repo.create_product(product)

    async def list_products(self, company_id):
        return await self.repo.list_products(company_id)
