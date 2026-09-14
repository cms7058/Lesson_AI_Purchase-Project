from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentUser, UserRole, get_current_user
from app.domain.common import Page
from app.domain.connectors import ConnectorCreate, ConnectorUpdate, DataConnector
from app.domain.persistence import DataConnectorRecord
from app.domain.supply_feedback import SupplyFeedback
from app.services.audit_service import write_audit_log

router = APIRouter(prefix="/data-connectors", tags=["data-connectors"])

from app.core.security import require_roles
from app.services.api_probe import Probe, probe


@router.post('/test-api', dependencies=[Depends(require_roles(UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER))])
def test_api(payload: Probe):
    return probe(payload)


@router.get("", response_model=Page[DataConnector])
def list_connectors(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), keyword: str = Query("", max_length=100), db: Session = Depends(get_db)) -> Page[DataConnector]:
    filters = []
    if keyword:
        pattern = f"%{keyword.strip()}%"
        filters.append(or_(DataConnectorRecord.name.ilike(pattern), DataConnectorRecord.base_url.ilike(pattern)))
    total = db.scalar(select(func.count()).select_from(DataConnectorRecord).where(*filters)) or 0
    records = db.scalars(select(DataConnectorRecord).where(*filters).order_by(DataConnectorRecord.created_at.desc()).offset((page - 1) * page_size).limit(page_size))
    return Page(items=list(records), page=page, page_size=page_size, total=total)


@router.post("", response_model=DataConnector, status_code=status.HTTP_201_CREATED)
def create_connector(
    payload: ConnectorCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> DataConnectorRecord:
    if current_user.role not in {UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前角色无权配置系统连接器")
    connector = DataConnectorRecord(
        name=payload.name,
        connector_type=payload.connector_type,
        base_url=payload.base_url,
        sync_mode=payload.sync_mode,
        status="draft",
        created_by=current_user.user_id,
    )
    db.add(connector)
    try:
        db.flush()
        write_audit_log(
            db,
            actor_id=current_user.user_id,
            actor_role=current_user.role,
            action="create",
            resource_type="data_connector",
            resource_id=connector.id,
            detail=f"创建连接器 {connector.name}",
        )
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="连接器名称已存在") from error
    db.refresh(connector)
    return connector


@router.patch("/{connector_id}", response_model=DataConnector)
def update_connector(connector_id: str, payload: ConnectorUpdate, db: Session = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)) -> DataConnectorRecord:
    if current_user.role not in {UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER}:
        raise HTTPException(status_code=403, detail="当前角色无权修改系统连接器")
    connector = db.get(DataConnectorRecord, connector_id)
    if connector is None:
        raise HTTPException(status_code=404, detail="未找到系统连接器")
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(connector, key, value.value if hasattr(value, "value") else value)
    try:
        db.flush()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="连接器名称已存在") from error
    write_audit_log(db, actor_id=current_user.user_id, actor_role=current_user.role, action="update", resource_type="data_connector", resource_id=connector_id, detail=f"更新连接器 {connector.name}")
    db.commit(); db.refresh(connector)
    return connector


@router.delete("/{connector_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_connector(connector_id: str, db: Session = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)) -> None:
    if current_user.role not in {UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER}:
        raise HTTPException(status_code=403, detail="当前角色无权删除系统连接器")
    connector = db.get(DataConnectorRecord, connector_id)
    if connector is None:
        raise HTTPException(status_code=404, detail="未找到系统连接器")
    name = connector.name
    if db.scalar(select(SupplyFeedback.id).where(SupplyFeedback.connector_id == connector_id).limit(1)):
        raise HTTPException(409, "连接器已有供货反馈记录，请停用而不是删除")
    db.delete(connector)
    write_audit_log(db, actor_id=current_user.user_id, actor_role=current_user.role, action="delete", resource_type="data_connector", resource_id=connector_id, detail=f"删除连接器 {name}")
    db.commit()
