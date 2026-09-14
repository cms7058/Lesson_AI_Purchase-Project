from fastapi import HTTPException
from sqlalchemy import select


def protect_references(db, checks, label):
    for model, condition in checks:
        if db.scalar(select(model.id).where(condition).limit(1)) is not None:
            raise HTTPException(status_code=409, detail=f"{label}已被业务记录引用，不能删除；可停用或保留历史")
