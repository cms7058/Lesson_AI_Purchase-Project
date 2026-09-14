from collections import defaultdict

from sqlalchemy import select

from app.domain.persistence import GoodsReceiptRecord, PurchaseOrderLineRecord, StaffUserRecord


def buyer_statistics(db, base):
    staff = {s.id: f"{s.name}（{s.user_code}）" for s in db.scalars(select(StaffUserRecord))}
    orders = {r.id: r for r in db.execute(select(base)).all()}
    groups = {}
    supplier_groups = {}
    def empty(key, name):
        return {"key": key, "name": name, "order_count": 0, "amount": 0, "supplier_count": 0, "receipt_count": 0, "eligible_receipts": 0, "on_time_receipts": 0, "on_time_rate": None}
    suppliers = defaultdict(set)
    for row in orders.values():
        key = row.buyer_id or "unassigned"
        group = groups.setdefault(key, empty(key, staff.get(key, "未分配采购员")))
        group["order_count"] += 1
        group["amount"] += float(row.amount)
        suppliers[key].add(row.supplier_name)
    # A receipt is comparable only when its material has one unambiguous promised date.
    promises = defaultdict(set)
    for line in db.scalars(select(PurchaseOrderLineRecord).where(PurchaseOrderLineRecord.order_id.in_(select(base.c.id)))):
        promises[(line.order_id, line.material_code)].add(line.delivery_date)
    for receipt in db.scalars(select(GoodsReceiptRecord).where(GoodsReceiptRecord.order_id.in_(select(base.c.id)), GoodsReceiptRecord.status.in_(["received", "inspected"]))):
        order = orders[receipt.order_id]
        key = order.buyer_id or "unassigned"
        group = groups[key]
        supplier_key = (key, order.supplier_name)
        sg = supplier_groups.setdefault(supplier_key, {"buyer": group["name"], "supplier": order.supplier_name, "receipt_count": 0, "eligible_receipts": 0, "on_time_receipts": 0, "on_time_rate": None})
        for target in [group, sg]:
            target["receipt_count"] += 1
            dates = promises[(receipt.order_id, receipt.material_code)]
            if len(dates) == 1 and None not in dates and receipt.received_date:
                target["eligible_receipts"] += 1
                if receipt.received_date <= next(iter(dates)):
                    target["on_time_receipts"] += 1
    for key, group in groups.items():
        group["supplier_count"] = len(suppliers[key])
        group["amount"] = round(group["amount"], 2)
    for group in list(groups.values()) + list(supplier_groups.values()):
        if group["eligible_receipts"]:
            group["on_time_rate"] = round(group["on_time_receipts"] / group["eligible_receipts"] * 100, 2)
    return sorted(groups.values(), key=lambda x: -x["amount"]), sorted(supplier_groups.values(), key=lambda x: (x["buyer"], x["supplier"]))
