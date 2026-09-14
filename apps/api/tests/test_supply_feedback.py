import csv
import io
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.database import SessionLocal
from app.domain.supply_feedback import AwardAnalysisSnapshot, FeedbackRow, SupplyFeedback
from app.main import app
from app.services.supply_analysis import cost_profile, distribution

client = TestClient(app)
H = {"X-User-Role": "procurement_manager"}


@pytest.fixture
def setup_feedback():
    tag = uuid4().hex[:8]
    supplier = client.post("/api/v1/suppliers", headers=H, json={"code":"FB-S-"+tag,"name":"反馈供应商"}).json()
    material = client.post("/api/v1/materials", headers=H, json={"code":"FB-M-"+tag,"name":"反馈物料"}).json()
    connector = client.post("/api/v1/data-connectors", headers=H, json={"name":"MES-"+tag,"connector_type":"mes"}).json()
    client.patch("/api/v1/data-connectors/"+connector["id"], headers=H, json={"status":"active"})
    token = client.post(f"/api/v1/data-connectors/{connector['id']}/feedback-token", headers=H).json()["token"]
    row = {"external_id":"BATCH1","supplier_code":supplier["code"],"material_code":material["code"],"record_date":"2026-08-01","received_quantity":100,"inspected_quantity":100,"accepted_quantity":95,"on_time_quantity":90,"rework_quantity":3,"response_hours":4,"unit_price":50,"costs_confirmed":True}
    return connector, row, token


def test_push_scope_idempotency_and_atomic_conflict(setup_feedback):
    connector, row, token = setup_feedback
    url = "/api/v1/integration-feedback/"+connector["id"]
    auth = {"Authorization":"Bearer "+token}
    assert client.post(url, json={"rows":[row]}).status_code == 401
    assert client.post(url, headers=auth, json={"rows":[row]}).json()["inserted"] == 1
    assert client.post(url, headers=auth, json={"rows":[row]}).json()["skipped"] == 1
    conflict = client.post(url, headers=auth, json={"rows":[{**row,"external_id":"BATCH2"},{**row,"accepted_quantity":90}]})
    assert conflict.status_code == 409
    assert client.get("/api/v1/supply-feedback/records", headers=H, params={"connector_id":connector["id"]}).json()["total"] == 1
    client.post(f"/api/v1/data-connectors/{connector['id']}/feedback-token", headers=H)
    assert client.post(url, headers=auth, json={"rows":[row]}).status_code == 401


def test_csv_import_and_metric_formulas(setup_feedback):
    connector, row, _ = setup_feedback
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer,fieldnames=list(row))
    writer.writeheader()
    for i, quality in enumerate([90,95,100]):
        writer.writerow({**row,"external_id":f"CSV-{i}","accepted_quantity":quality})
    response = client.post(f"/api/v1/data-connectors/{connector['id']}/feedback-import", headers=H, files={"file":("feedback.csv",buffer.getvalue().encode())})
    assert response.status_code == 200, response.text
    stats = client.get("/api/v1/supplier-metrics/statistics", headers=H, params={"supplier_code":row["supplier_code"],"material_code":row["material_code"],"metric":"quality","page_size":2}).json()
    assert stats["statistics"]["median"] == 95 and stats["statistics"]["mean"] == 95
    assert stats["statistics"]["n"] == 3 and len(stats["items"]) == 2
    assert stats["statistics"]["normal_curve"] and stats["statistics"]["qq"]
    template = client.get("/api/v1/supply-feedback/template", headers=H)
    assert template.status_code == 200 and "received_quantity" in template.text
    bad = client.post(f"/api/v1/data-connectors/{connector['id']}/feedback-import",headers=H,files={"file":("bad.csv",b"external_id,supplier_code\nbad,unknown")})
    assert bad.status_code == 422


def test_manual_metrics_rejected_and_zero_yield_preserved():
    assert client.post("/api/v1/suppliers",headers=H,json={"code":"MANUAL-BAD","name":"不可手填","quality_pass_rate":99}).status_code == 422
    assert distribution([])["median"] is None
    assert distribution([1,1,1])["p_value"] is None
    rows = [FeedbackRow(external_id=str(i),supplier_code="S",material_code="M",record_date="2026-01-01",received_quantity=10,inspected_quantity=10,accepted_quantity=0,unit_price=10,costs_confirmed=True).model_dump(mode="json") for i in range(3)]
    profile = cost_profile(rows,"CNY","件")
    assert profile["n"] == 3 and profile["median_yield"] == 0 and profile["regression"] is None


def test_complete_template_round_trip_and_malformed_csv(setup_feedback):
    connector, row, _ = setup_feedback
    template = client.get('/api/v1/supply-feedback/template', headers=H)
    fields = next(csv.reader(io.StringIO(template.content.decode('utf-8-sig'))))
    assert set(fields) == set(FeedbackRow.model_fields)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    writer.writerow({**row, 'metrics_available_date': '2026-08-02'})
    url = f"/api/v1/data-connectors/{connector['id']}/feedback-import"
    data = buffer.getvalue()
    assert client.post(url, headers=H, files={'file': ('toc.csv', data.encode())}).json()['inserted'] == 1
    assert client.post(url, headers=H, files={'file': ('toc.csv', data.encode())}).json()['skipped'] == 1
    for malformed in [data.rstrip() + ',extra\n', data.replace('external_id,', 'typo_id,', 1)]:
        response = client.post(url, headers=H, files={'file': ('bad.csv', malformed.encode())})
        assert response.status_code == 422, response.text
    records = client.get('/api/v1/supply-feedback/records', headers=H, params={'connector_id': connector['id']}).json()
    assert records['total'] == 1
    assert records['items'][0]['metrics_available_date'] == '2026-08-02'
    assert client.post(url, headers={'X-User-Role': 'buyer'}, files={'file': ('toc.csv', data.encode())}).status_code in (403, 422)


def test_demo_tco_regression_and_award_snapshot():
    demo = client.post("/api/v1/supply-feedback/demo",headers=H)
    assert demo.status_code == 200,demo.text
    rfq_id = demo.json()["rfq_id"]
    assert client.post("/api/v1/supply-feedback/demo",headers=H).json()["inserted"] == 0
    actual = client.get(f"/api/v1/rfqs/{rfq_id}/award-analysis",headers=H).json()
    assert not actual["tco_ready"]
    analysis = client.get(f"/api/v1/rfqs/{rfq_id}/award-analysis?include_demo=true",headers=H).json()
    assert analysis["tco_ready"] and analysis["lowest_ids"] != analysis["tco_ids"]
    assert all(m["profile"]["regression"] for r in analysis["items"] for m in r["materials"])
    chosen = analysis["tco_ids"][0]
    assert client.post(f"/api/v1/rfqs/{rfq_id}/award",headers=H,json={"quotation_id":chosen,"method":"tco"}).status_code == 409
    # Test-only conversion of isolated fixture rows to real records exercises formal award.
    with SessionLocal.begin() as db:
        for row in db.scalars(select(SupplyFeedback).where(SupplyFeedback.is_demo.is_(True))):
            row.is_demo = False
    result = client.post(f"/api/v1/rfqs/{rfq_id}/award",headers=H,json={"quotation_id":chosen,"method":"tco"})
    assert result.status_code == 200,result.text
    with SessionLocal() as db:
        snapshot = db.scalar(select(AwardAnalysisSnapshot).where(AwardAnalysisSnapshot.rfq_id==rfq_id))
        assert snapshot.method == "tco" and snapshot.quotation_id == chosen
