"""Create the teaching database and optionally add idempotent demo fixtures."""
import json
import os

from app.core.database import Base, SessionLocal, engine
import app.domain.teaching  # noqa: F401  Ensure login/learning tables are registered before create_all.
from app.seed_demo import seed


def enabled(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


Base.metadata.create_all(bind=engine)
result = {"schema": "ready", "demo_data": "disabled"}
if enabled(os.getenv("SEED_DEMO_DATA", "true")):
    with SessionLocal.begin() as session:
        counts = seed(session)
    result["demo_data"] = "ready"
    result["inserted"] = counts

print(json.dumps(result, ensure_ascii=False))
