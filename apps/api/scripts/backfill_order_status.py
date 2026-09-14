"""Reconcile historical order states after enabling fulfillment tracking.

Run from apps/api: PYTHONPATH=. .venv/bin/python scripts/backfill_order_status.py
Use --apply only after backing up the configured database.
"""
import argparse

from sqlalchemy import select

from app.core.database import SessionLocal
from app.domain.persistence import PurchaseOrderRecord
from app.services.audit_service import write_audit_log
from app.services.order_service import fulfillment_status


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    changes = 0
    with SessionLocal() as db:
        for order in db.scalars(select(PurchaseOrderRecord).where(PurchaseOrderRecord.status != "cancelled")):
            derived = fulfillment_status(db, order)
            if derived and derived != order.status:
                print(f"{order.order_no}: {order.status} -> {derived}")
                changes += 1
                if args.apply:
                    order.status = derived
                    write_audit_log(db, actor_id="order-status-backfill", actor_role="admin", action="sync_status", resource_type="purchase_order", resource_id=order.id, detail="依据已有收货、质检与退货记录同步采购状态")
        if args.apply:
            db.commit()
    print(f"{'Updated' if args.apply else 'Would update'} {changes} orders")


if __name__ == "__main__":
    main()
