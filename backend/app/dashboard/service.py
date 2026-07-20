from app.dashboard.repository import DashboardRepository


class DashboardService:
    def __init__(self, repo: DashboardRepository):
        self.repo = repo

    async def get_summary(self, company_id):
        return await self.repo.get_summary(company_id)
