from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, update

from app.api.routes.projects import get_record
from app.core.database import get_db
from app.core.security import UserRole, get_current_user, require_roles
from app.domain.persistence import PurchaseOrderLineRecord, PurchaseOrderRecord
from app.domain.project_costs import AllocationInput, ProjectAllocation
from app.domain.projects import project_data
from app.services.audit_service import write_audit_log

router = APIRouter(prefix='/project-costs', tags=['project-costs'], dependencies=[Depends(require_roles(UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER))])


@router.get('/lines')
def lines(keyword: str = '', currency: str = 'CNY', page: int = Query(1, ge=1), db=Depends(get_db)):
    filters = [PurchaseOrderRecord.currency == currency, PurchaseOrderRecord.status != 'cancelled']
    if keyword:
        filters.append(PurchaseOrderRecord.order_no.contains(keyword) | PurchaseOrderLineRecord.material_code.contains(keyword))
    query = select(PurchaseOrderLineRecord, PurchaseOrderRecord).join(PurchaseOrderRecord).where(*filters)
    total = db.scalar(select(func.count()).select_from(PurchaseOrderLineRecord).join(PurchaseOrderRecord).where(*filters))
    rows = db.execute(query.order_by(PurchaseOrderLineRecord.id.desc()).offset((page-1)*10).limit(10)).all()
    return {'total': total, 'items': [{'id': l.id, 'order_no': o.order_no, 'material_code': l.material_code, 'quantity': float(l.quantity), 'unit_price': float(l.unit_price), 'allocated': float(db.scalar(select(func.sum(ProjectAllocation.quantity)).where(ProjectAllocation.line_id == l.id)) or 0)} for l, o in rows]}


def summary(db, project_id):
    project = project_data(get_record(db, project_id))
    allocations = list(db.scalars(select(ProjectAllocation).where(ProjectAllocation.project_id == project_id)))
    totals = {'draft': Decimal(0), 'committed': Decimal(0), 'cancelled': Decimal(0)}
    rows = []
    for a in allocations:
        line = db.get(PurchaseOrderLineRecord, a.line_id)
        order = db.get(PurchaseOrderRecord, a.order_id)
        if not line or not order:
            raise HTTPException(409, '关联订单明细缺失，需修复引用后再计算')
        amount = (a.quantity * line.unit_price * (1 + line.tax_rate)).quantize(Decimal('.01'))
        category = 'cancelled' if order.status == 'cancelled' else 'draft' if order.status in ('draft', 'pending_approval') else 'committed'
        totals[category] += amount
        rows.append({'id': a.id, 'line_id': a.line_id, 'task_id': a.task_id, 'order_no': order.order_no, 'material_code': line.material_code, 'quantity': float(a.quantity), 'amount': float(amount), 'category': category})
    return {'project': project, 'rows': rows, **{k: float(v) for k, v in totals.items()}, 'over_budget': totals['committed'] > Decimal(str(project['budget']))}


@router.get('/{project_id}')
def get_costs(project_id: str, db=Depends(get_db)):
    return summary(db, project_id)


def save_allocation(db, project_id, data, item=None):
    project = project_data(get_record(db, project_id))
    if project['status'] in ('completed', 'archived'):
        raise HTTPException(409, '完成或归档项目不能调整分摊')
    if data.task_id and not any(t['id'] == data.task_id for t in project['tasks']):
        raise HTTPException(422, '关联任务不存在')
    # A write lock serializes quantity checks for SQLite and PostgreSQL.
    db.execute(update(PurchaseOrderLineRecord).where(PurchaseOrderLineRecord.id == data.line_id).values(quantity=PurchaseOrderLineRecord.quantity))
    line = db.get(PurchaseOrderLineRecord, data.line_id)
    if not line:
        raise HTTPException(404, '订单明细不存在')
    order = db.get(PurchaseOrderRecord, line.order_id)
    if order.currency != project['currency'] or order.status == 'cancelled':
        raise HTTPException(409, '订单币种不匹配或已取消')
    allocated = db.scalar(select(func.sum(ProjectAllocation.quantity)).where(ProjectAllocation.line_id == line.id, ProjectAllocation.id != (item.id if item else ''))) or Decimal(0)
    if allocated + data.quantity > line.quantity:
        raise HTTPException(409, '各项目分摊数量合计不能超过订单行数量')
    row = item or ProjectAllocation(project_id=project_id)
    row.line_id, row.order_id, row.task_id, row.quantity = line.id, line.order_id, data.task_id, data.quantity
    db.add(row)
    db.flush()
    return row


@router.post('/{project_id}')
def create(project_id: str, data: AllocationInput, db=Depends(get_db), user=Depends(get_current_user)):
    row = save_allocation(db, project_id, data)
    write_audit_log(db, actor_id=user.user_id, actor_role=user.role, action='allocate', resource_type='project_cost', resource_id=row.id, detail=f'项目{project_id}分摊订单行{data.line_id}数量{data.quantity}')
    db.commit()
    return {'id': row.id}


@router.put('/{project_id}/{item_id}')
def edit(project_id: str, item_id: str, data: AllocationInput, db=Depends(get_db), user=Depends(get_current_user)):
    row = db.get(ProjectAllocation, item_id)
    if not row or row.project_id != project_id:
        raise HTTPException(404, '分摊不存在')
    if data.line_id != row.line_id:
        raise HTTPException(409, '更换订单行请先移除原分摊')
    save_allocation(db, project_id, data, row)
    write_audit_log(db, actor_id=user.user_id, actor_role=user.role, action='update', resource_type='project_cost', resource_id=row.id, detail=f'调整分摊数量为{data.quantity}')
    db.commit()
    return {'id': row.id}


@router.delete('/{project_id}/{item_id}', status_code=204)
def remove(project_id: str, item_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    project = get_record(db, project_id)
    row = db.get(ProjectAllocation, item_id)
    if not row or row.project_id != project_id:
        raise HTTPException(404, '分摊不存在')
    if project.status in ('completed', 'archived'):
        raise HTTPException(409, '完成或归档项目不能调整分摊')
    db.delete(row)
    write_audit_log(db, actor_id=user.user_id, actor_role=user.role, action='delete', resource_type='project_cost', resource_id=item_id, detail='解除项目采购分摊')
    db.commit()
