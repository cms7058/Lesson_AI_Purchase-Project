"""Create the teaching database and optionally add idempotent demo fixtures."""
import json
import os

from app.core.database import Base, SessionLocal, engine
from app.domain.model_registry import load_all_models
from app.seed_demo import seed as seed_core


def enabled(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


load_all_models()
Base.metadata.create_all(bind=engine)
result = {"schema": "ready", "demo_data": "disabled"}
if enabled(os.getenv("SEED_DEMO_DATA", "true")):
    seed_steps = [
        ("core", seed_core),
        ("aviation", "app.seed_aviation_demo", "seed"),
        ("mro_intelligence", "app.seed_mro_intelligence_demo", "seed"),
        ("projects", "app.seed_project_demo", "seed"),
        ("spares", "app.seed_spare_demo", "seed"),
        ("spare_doe", "app.seed_spare_doe_demo", "seed"),
        ("knowledge", "app.seed_knowledge_demo", "seed"),
    ]
    counts = {}
    for step in seed_steps:
        if step[0] == "core":
            function = step[1]
        else:
            from importlib import import_module

            function = getattr(import_module(step[1]), step[2])
        with SessionLocal() as session:
            value = function(session)
            session.commit()
        counts[step[0]] = value
    from app.seed_spare_operations_demo import run as seed_spare_operations

    counts["spare_operations"] = seed_spare_operations()
    result["demo_data"] = "ready"
    result["inserted"] = counts

print(json.dumps(result, ensure_ascii=False))
