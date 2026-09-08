from app.dashboard.repository import DashboardRepository


class DashboardService:
    def __init__(self, repo: DashboardRepository):
        self.repo = repo

    async def get_summary(self, company_id):
        return await self.repo.get_summary(company_id)

    async def get_phase2_summary(
        self,
        company_id,
        *,
        range_key,
        date_from=None,
        date_to=None,
        shop_id=None,
    ):
        return await self.repo.get_phase2_summary(
            company_id,
            range_key=range_key,
            date_from=date_from,
            date_to=date_to,
            shop_id=shop_id,
        )
