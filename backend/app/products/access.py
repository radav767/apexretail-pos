"""Shared existing catalogue-read policy for routes and direct read services."""
from fastapi import HTTPException
from app.auth.dependencies import ensure_company_access


def ensure_catalog_access(actor,company_id):
    ensure_company_access(actor,company_id)
    if actor.actor_type=='employee' and actor.role not in {'owner','manager','administrator'}:
        if not any((actor.permissions or {}).get(key) for key in ('sales','manage_products','manage_inventory')):
            raise HTTPException(403,'Permission denied')
