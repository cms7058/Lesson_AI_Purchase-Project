from app.core.database import Base
from app.domain.model_registry import load_all_models


def test_registry_contains_project_and_teaching_tables():
    load_all_models()
    required = {
        "managed_projects",
        "project_baselines",
        "project_staff_grants",
        "project_purchase_allocations",
        "project_notifications",
        "system_sessions",
        "learning_accounts",
        "exam_attempts",
        "training_materials",
    }
    assert required <= set(Base.metadata.tables)
