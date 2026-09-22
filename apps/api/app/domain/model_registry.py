"""Register every SQLAlchemy model used by the application.

Production schema bootstrap does not import the API router, so model modules must
be loaded explicitly before ``Base.metadata.create_all`` is called.
"""
from importlib import import_module

MODEL_MODULES = (
    # These two legacy route modules still own their SQLAlchemy records. Keep
    # them in the bootstrap registry until the models are moved to domain files.
    "app.api.routes.doe",
    "app.api.routes.strategy_decision",
    "app.domain.aviation_mro",
    "app.domain.contract_reviews",
    "app.domain.equipment_mro",
    "app.domain.inventory_intelligence",
    "app.domain.knowledge",
    "app.domain.material_documents",
    "app.domain.material_governance",
    "app.domain.material_policy",
    "app.domain.mro_intelligence",
    "app.domain.order_buyer",
    "app.domain.persistence",
    "app.domain.project_access",
    "app.domain.project_costs",
    "app.domain.project_notifications",
    "app.domain.projects",
    "app.domain.spare_operations",
    "app.domain.spares",
    "app.domain.supplier_execution",
    "app.domain.supplier_portal",
    "app.domain.supplier_qualifications",
    "app.domain.supply_feedback",
    "app.domain.teaching",
)


def load_all_models() -> None:
    for module_name in MODEL_MODULES:
        import_module(module_name)
