from fastapi import HTTPException
from sqlalchemy import func, or_, select

from app.employees.permissions import PERMISSION_GROUPS, PERMISSION_KEYS, ROLE_TEMPLATES, has_permission, normalize_permissions
from app.models import AuditEvent, Employee, EmployeeRole, User


class EmployeeAdminService:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def _actor_ids(actor):
        return {
            "actor_employee_id": actor.employee.id if actor.actor_type == "employee" else None,
            "actor_user_id": actor.user.id if actor.actor_type == "user" else None,
        }

    @staticmethod
    def ensure_grantable(actor, permissions):
        if actor.actor_type == "user" and actor.role in {"owner", "administrator"}:
            return
        for key, enabled in permissions.items():
            if enabled and not has_permission(actor.permissions, key):
                raise HTTPException(403, f"Cannot grant permission: {key}")

    @staticmethod
    def authorize(company_id, actor):
        from app.sales.commands import actor_identity
        from app.printing.service import permit
        actor_identity(actor, company_id)
        permit(actor, 'employees_manage')

    async def list_roles(self, company_id):
        rows = (await self.db.execute(select(EmployeeRole).where(
            EmployeeRole.company_id == company_id,
            EmployeeRole.deleted == False,
        ).order_by(EmployeeRole.name))).scalars().all()
        builtins = [{
            "id": None, "company_id": company_id, "name": name,
            "description": "Built-in role", "permissions": normalize_permissions(name, permissions),
            "active": True, "system": True,
        } for name, permissions in ROLE_TEMPLATES.items()]
        custom = [{
            "id": row.id, "company_id": row.company_id, "name": row.name,
            "description": row.description, "permissions": normalize_permissions("denied", row.permissions),
            "active": row.active, "system": False,
        } for row in rows]
        return builtins + custom

    async def create_role(self, data, actor):
        self.authorize(data.company_id, actor)
        from app.subscriptions.write_policy import require_new_write
        await require_new_write(self.db, data.company_id)
        self.ensure_grantable(actor, data.permissions)
        name = data.name.strip()
        if name.lower().replace(" ", "_") in {*ROLE_TEMPLATES, "manager"}:
            raise HTTPException(409, "That role name is reserved")
        existing = (await self.db.execute(select(EmployeeRole.id).where(
            EmployeeRole.company_id == data.company_id,
            func.lower(EmployeeRole.name) == name.lower(),
            EmployeeRole.deleted == False,
        ))).scalar_one_or_none()
        if existing:
            raise HTTPException(409, "A role with this name already exists")
        role = EmployeeRole(
            company_id=data.company_id, name=name,
            description=(data.description or "").strip() or None,
            permissions=normalize_permissions("denied", data.permissions),
        )
        self.db.add(role)
        await self.db.flush()
        self.db.add(AuditEvent(
            company_id=data.company_id, action="role_created",
            details={"role_id": str(role.id), "role_name": role.name},
            **self._actor_ids(actor),
        ))
        await self.db.commit()
        await self.db.refresh(role)
        return {"id": role.id, "company_id": role.company_id, "name": role.name, "description": role.description, "permissions": role.permissions, "active": role.active, "system": False}

    async def update_role(self, company_id, role_id, data, actor):
        self.authorize(company_id, actor)
        if data.permissions is not None:
            self.ensure_grantable(actor, data.permissions)
        role = (await self.db.execute(select(EmployeeRole).where(
            EmployeeRole.id == role_id, EmployeeRole.company_id == company_id,
            EmployeeRole.deleted == False,
        ).with_for_update())).scalar_one_or_none()
        if role is None:
            raise HTTPException(404, "Role not found")
        requested = {key for key,value in data.model_dump(exclude_unset=True).items() if value is not None}
        preview = role.permissions if data.permissions is None else normalize_permissions('denied', data.permissions)
        adds_rights = any(has_permission(preview,key) and not has_permission(role.permissions,key) for key in PERMISSION_KEYS)
        security_only = (bool(requested) and requested <= {'permissions','active'} and not adds_rights and
                         not (data.active is True and not role.active))
        if not security_only:
            from app.subscriptions.write_policy import require_new_write
            await require_new_write(self.db, company_id)
        before = {"name": role.name, "permissions": role.permissions, "active": role.active}
        if data.name is not None:
            name = data.name.strip()
            if name.lower().replace(" ", "_") in {*ROLE_TEMPLATES, "manager"}:
                raise HTTPException(409, "That role name is reserved")
            duplicate = (await self.db.execute(select(EmployeeRole.id).where(
                EmployeeRole.company_id == company_id,
                func.lower(EmployeeRole.name) == name.lower(),
                EmployeeRole.id != role_id,
                EmployeeRole.deleted == False,
            ))).scalar_one_or_none()
            if duplicate:
                raise HTTPException(409, "A role with this name already exists")
            role.name = name
        if data.description is not None:
            role.description = data.description.strip() or None
        if data.permissions is not None:
            role.permissions = normalize_permissions("denied", data.permissions)
        if data.active is not None:
            role.active = data.active
        assigned = (await self.db.execute(select(Employee).where(
            Employee.company_id == company_id, Employee.role_id == role.id,
            Employee.deleted == False,
        ).with_for_update())).scalars().all()
        revoked = []
        for employee in assigned:
            previous = (employee.role, dict(employee.permissions or {}))
            employee.role = "custom"
            employee.permissions = normalize_permissions(
                "kitchen_staff",
                {**role.permissions, **(employee.role_overrides or {})},
            ) if role.active else normalize_permissions("denied", {})
            if (employee.role, dict(employee.permissions or {})) != previous:
                from .revocation import revoke
                employee.session_version = await revoke(self.db, company_id, employee.id, 'role_security_changed')
                revoked.append(str(employee.id))
        self.db.add(AuditEvent(
            company_id=company_id, action="role_updated",
            details={"role_id": str(role.id), "before": before, "after": {"name": role.name, "permissions": role.permissions, "active": role.active}, "revoked_employee_ids": revoked},
            **self._actor_ids(actor),
        ))
        await self.db.commit()
        return {"id": role.id, "company_id": role.company_id, "name": role.name, "description": role.description, "permissions": role.permissions, "active": role.active, "system": False}

    async def permission_catalog(self):
        return PERMISSION_GROUPS

    async def audit_log(self, company_id, action=None, employee_id=None, limit=100, actor=None):
        query = select(
            AuditEvent.id, AuditEvent.actor_employee_id, AuditEvent.actor_user_id,
            AuditEvent.device_id, AuditEvent.action, AuditEvent.reason,
            AuditEvent.details, AuditEvent.created_at,
            func.coalesce(Employee.name, User.email).label("actor_name"),
        ).outerjoin(Employee, Employee.id == AuditEvent.actor_employee_id).outerjoin(
            User, User.id == AuditEvent.actor_user_id
        ).where(AuditEvent.company_id == company_id)
        if actor is not None and actor.actor_type == "employee" and actor.role not in {"owner", "administrator"}:
            query = query.where(Employee.branch_id == actor.employee.branch_id)
        if action:
            query = query.where(AuditEvent.action == action)
        if employee_id:
            query = query.where(or_(AuditEvent.actor_employee_id == employee_id,
                                     AuditEvent.details["employee_id"].as_string() == str(employee_id)))
        result = await self.db.execute(query.order_by(AuditEvent.created_at.desc()).limit(limit))
        return [dict(row) for row in result.mappings().all()]
