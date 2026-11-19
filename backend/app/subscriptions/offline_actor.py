"""Fresh current permissions for an opaque, register-bound offline grant."""
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import select
from app.models import Device, Employee, EmployeeDeviceAccess, EmployeeShopAccess, PosSession
from app.employees.permissions import has_permission


async def grant_for(db, actor):
    identity = actor.employee if actor.actor_type == 'employee' else actor.user
    grant = {'actor_type':actor.actor_type, 'actor_id':str(identity.id), 'session_version':identity.session_version,
             'branch_id':None, 'device_id':None, 'assignment_revision':None,
             'actions':{name:False for name in ('sale','draft','kitchen','kitchen_update','bar_update')}}
    if actor.actor_type != 'employee' or actor.pos_session is None:
        return grant  # Online identity is not an offline register authorization.
    authenticated_hash = actor.pos_session.token_hash
    # Employee->Device->PosSession ordering is compatible with logout/security
    # changes and PIN takeover. Shared-role updates cannot commit an epoch while
    # this grant is being built. Never acquire a role row lock after Employee.
    employee = (await db.execute(select(Employee).where(Employee.id == identity.id,
        Employee.company_id == actor.company_id).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    if (not employee or not employee.active or employee.deleted or
            actor.authenticated_session_version != employee.session_version):
        raise HTTPException(401, 'Employee session is no longer valid')
    session = actor.pos_session
    device = (await db.execute(select(Device).where(Device.id == session.device_id,
        Device.company_id == actor.company_id).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    current = (await db.execute(select(PosSession).where(PosSession.id == session.id,
        PosSession.company_id == actor.company_id).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    if current and current.token_hash != authenticated_hash:
        raise HTTPException(401, 'Employee session is no longer valid')
    if (not current or current.revoked_at or current.expires_at <= datetime.now(timezone.utc) or
            current.employee_id != employee.id or current.session_version != employee.session_version or
            not device or not device.active or device.deleted or device.removed_at or device.deactivated_at or
            current.device_id != device.id or current.branch_id != device.branch_id or current.shop_id != device.shop_id):
        raise HTTPException(403, 'A current device-bound PIN session is required for offline access')
    if employee.role not in {'owner', 'administrator'} and employee.branch_id != device.branch_id:
        raise HTTPException(403, 'Employee branch access changed; sign in again')
    if employee.role != 'owner':
        shops = (await db.execute(select(EmployeeShopAccess.shop_id).where(
            EmployeeShopAccess.employee_id == employee.id))).scalars().all() or [employee.shop_id]
        if device.shop_id not in shops: raise HTTPException(403, 'Employee shop access changed; sign in again')
    if employee.device_restricted and (await db.execute(select(EmployeeDeviceAccess.id).where(
            EmployeeDeviceAccess.employee_id == employee.id, EmployeeDeviceAccess.device_id == device.id))).scalar_one_or_none() is None:
        raise HTTPException(403, 'Employee register access changed; sign in again')
    from app.employees.service import EmployeeService
    permissions = await EmployeeService.effective_permissions(employee, db)
    grant.update(session_version=employee.session_version, branch_id=str(device.branch_id), device_id=str(device.id),
                 assignment_revision=device.assignment_revision)
    grant['actions'] = {'sale':has_permission(permissions,'sales_process'), 'draft':has_permission(permissions,'orders_manage'),
        'kitchen':has_permission(permissions,'orders_manage') and has_permission(permissions,'orders_send'),
        'kitchen_update':has_permission(permissions,'kitchen_update'), 'bar_update':has_permission(permissions,'bar_update')}
    return grant
