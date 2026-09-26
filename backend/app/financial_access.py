from fastapi import HTTPException

from app.auth.dependencies import AuthActor


def enforce_actor_company(actor: AuthActor, company_id) -> None:
    if actor.company_id != company_id:
        raise HTTPException(403, "Forbidden")


def enforce_actor_branch(actor: AuthActor, branch_id) -> None:
    if actor.actor_type != "employee" or actor.role in {"owner", "administrator"}:
        return
    if actor.employee is None or actor.employee.branch_id != branch_id:
        raise HTTPException(403, "Branch access denied")
