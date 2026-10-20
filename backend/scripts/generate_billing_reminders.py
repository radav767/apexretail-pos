"""Authorized scheduler entry point. No scheduler/service is installed automatically.

Uses the configured database; production execution needs deployment approval.
Emits deduplicated IN-APP notices only, never claims external email delivery.
"""
import asyncio
from app.db.session import SessionLocal
from app.subscriptions.commercial import CommercialService
async def main():
    async with SessionLocal() as db:print(await CommercialService(db).reminders())
if __name__=='__main__':asyncio.run(main())
