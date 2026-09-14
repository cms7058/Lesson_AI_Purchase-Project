from sqlalchemy import select
from sqlalchemy.orm import Session


def next_sequence(db: Session, model, field: str, prefix: str) -> int:
    """Count-independent numbering; deleting a middle row cannot reuse a live number."""
    column = getattr(model, field)
    start = f"{prefix}-"
    values = db.scalars(select(column).where(column.startswith(start)))
    return max((int(value[len(start):]) for value in values if value[len(start):].isdigit()), default=0)
