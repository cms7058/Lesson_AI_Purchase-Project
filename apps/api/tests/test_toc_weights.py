import copy

import numpy as np
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.services.feedback_demo import seed_weight_demo
from app.services.supply_analysis import observations, rfq_analysis
from app.services.toc_weights import build_model, prepare, quote_prediction

client = TestClient(app)


def cohort():
    with SessionLocal() as db:
        demo = seed_weight_demo(db)
        return observations(db, material_code="DEMO-WT-M001", include_demo=True), demo["rfq_id"]


def test_learned_coefficients_weights_validation_and_reproducibility():
    rows, _ = cohort()
    model = build_model(rows, "CNY", "件")
    assert model["usable"], model["warnings"]
    assert model["n"] == 231
    assert abs(model["weight_sum"]-1) < 1e-12
    assert len({round(w["coefficient"], 2) for w in model["weights"]}) == 6
    assert model["validation"]["mae"] < model["validation"]["baseline_mae"]
    assert model["validation"]["r_squared"] > .9
    assert np.allclose([w["coefficient"] for w in model["weights"]], [1.15, .75, 1.8, .65, .9, .4], atol=.2)
    assert build_model(list(reversed(rows)), "CNY", "件")["weights"] == model["weights"]
    assert quote_prediction(model, "DEMO-WT-S1", 1e8, 10)["total"] is None
    assert quote_prediction(model, "missing", 100, 10)["total"] is None
    assert model["demo_count"] == 231


def test_holdout_never_changes_training_coefficients_and_lags_are_prior():
    rows, _ = cohort()
    original = build_model(rows, "CNY", "件")
    changed = copy.deepcopy(rows)
    for r in changed:
        if r["record_date"] >= original["validation"]["cutoff"]:
            r["other_cost"] += 10000
    altered = build_model(changed, "CNY", "件")
    assert [w["coefficient"] for w in original["weights"]] == [w["coefficient"] for w in altered["weights"]]
    samples, _, _ = prepare(rows, "CNY", "件")
    for sample in samples[:10]:
        previous = sorted([r for r in rows if r["supplier_code"] == sample["supplier"] and r["metrics_available_date"] < sample["date"]], key=lambda r:r["record_date"])[-5:]
        assert np.isclose(sample["x"][2], np.median([100-r["accepted_quantity"] for r in previous]))


def test_insufficient_constant_collinearity_and_missing_availability():
    rows, _ = cohort()
    assert not build_model(rows[:5], "CNY", "件")["usable"]
    constant = copy.deepcopy(rows)
    for r in constant:
        r["response_hours"] = 5
    m = build_model(constant, "CNY", "件")
    assert not m["usable"] and m["weights"][-1]["constant"]
    correlated = copy.deepcopy(rows)
    for r in correlated:
        r["rework_quantity"] = 100-r["accepted_quantity"]
    assert not build_model(correlated, "CNY", "件")["usable"]
    no_dates = [{**r, "metrics_available_date": None} for r in rows]
    assert not build_model(no_dates, "CNY", "件")["usable"]
    assert not build_model(rows, "USD", "件")["usable"]


def test_zero_yield_duplicates_and_demo_award_isolation():
    rows, rfq = cohort()
    zero = copy.deepcopy(rows)
    zero[0]["accepted_quantity"] = 0
    _, rejected, _ = prepare(zero+[zero[1]], "CNY", "件")
    assert rejected["零合格交付（单独风险事件）"] == 1
    assert rejected["重复业务批次"] == 1
    with SessionLocal() as db:
        demo = rfq_analysis(db, rfq, True)
        actual = rfq_analysis(db, rfq, False)
    assert demo["weight_models"]["DEMO-WT-M001"]["weights"]
    assert not demo["weight_models"]["DEMO-WT-M001"]["pricing_usable"]
    assert not demo["weight_models"]["DEMO-WT-M001"]["doe_validation"]["diagnostics"]["passed"]
    assert all(
        material["prediction"]["total"] is None
        for item in demo["items"]
        for material in item["materials"]
    )
    assert not actual["tco_ready"]
    response = client.post(f"/api/v1/rfqs/{rfq}/award", headers={"X-User-Role":"procurement_manager"}, json={"quotation_id":demo["items"][0]["quotation_id"], "method":"tco"})
    assert response.status_code == 409
