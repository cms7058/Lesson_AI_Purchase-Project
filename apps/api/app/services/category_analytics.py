from collections import defaultdict

from sqlalchemy import func, select

from app.domain.persistence import MaterialCategoryAssignmentRecord as Assignment
from app.domain.persistence import MaterialCategoryRecord as Category
from app.domain.persistence import MaterialRecord as Material
from app.domain.persistence import PurchaseOrderLineRecord as Line


def category_analytics(db, base):
    categories = {c.id: c for c in db.scalars(select(Category))}
    totals = defaultdict(float)
    timeline = defaultdict(lambda: defaultdict(float))
    month = func.substr(base.c.created_at, 1, 7)
    query = select(Assignment.category_id, month, func.sum(Line.quantity * Line.unit_price)).join(base, base.c.id == Line.order_id).outerjoin(Material, Material.code == Line.material_code).outerjoin(Assignment, Assignment.material_id == Material.id).group_by(Assignment.category_id, month)
    for category_id, period, amount in db.execute(query):
        chain = []
        node = categories.get(category_id)
        while node and node.id not in chain:
            chain.append(node.id)
            node = categories.get(node.parent_id)
        if not chain:
            chain = ["unclassified"]
        for key in chain:
            totals[key] += float(amount)
            timeline[key][period] += float(amount)
    result = []
    for key, value in totals.items():
        node = categories.get(key)
        result.append({"key": key, "name": f"{node.code} {node.name}" if node else "未分类", "level": node.level if node else 1, "parent_id": node.parent_id if node else None, "value": round(value, 2), "trend": [{"name": m, "value": round(v, 2)} for m, v in sorted(timeline[key].items())]})
    return sorted(result, key=lambda r: (r["level"], -r["value"], r["name"]))
