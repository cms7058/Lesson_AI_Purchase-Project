"""Time-ordered, lagged multivariate TOC model; no learned coefficient is fixed to one."""
import hashlib
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime

import numpy as np
from scipy import stats

FEATURES = [
    ("landed_price", "含税到货单价", "ERP采购价×(1+税率)+物流费/收货数量", "元/收货单位"),
    ("lead_time", "交期天数", "订单确认至实际到货的天数", "天"),
    ("defect", "历史不合格率", "100−合格数量/检验数量×100；取此前最近5批中位数", "百分点"),
    ("late", "历史延期率", "100−准时数量/收货数量×100；取此前最近5批中位数", "百分点"),
    ("rework", "历史返工率", "返工数量/检验数量×100；取此前最近5批中位数", "百分点"),
    ("response", "历史响应时长", "从请求到首次有效回复的小时数；取此前最近5批中位数", "小时"),
]
VERSION = "toc-ridge-lag5-v2-doe6"


def indicators(row):
    inspected, received = row.get("inspected_quantity"), row.get("received_quantity")
    if not inspected or not received or any(row.get(k) is None for k in ["accepted_quantity", "on_time_quantity", "rework_quantity", "response_hours"]):
        return None
    values = [100-100*row["accepted_quantity"]/inspected, 100-100*row["on_time_quantity"]/received, 100*row["rework_quantity"]/inspected, row["response_hours"]]
    return values if np.isfinite(values).all() else None


def prepare(rows, currency, unit):
    rejected = Counter()
    pool = []
    seen = set()
    today = datetime.now(UTC).date().isoformat()
    for r in sorted(rows, key=lambda r: (str(r.get("record_date", "")), r.get("external_id", ""))):
        identity = (r.get("source_system"), r.get("supplier_code"), r.get("external_id"))
        if identity in seen:
            rejected["重复业务批次"] += 1
            continue
        seen.add(identity)
        if r.get("currency") != currency or r.get("unit") != unit:
            rejected["币种或单位不一致"] += 1
        elif str(r.get("record_date", "")) > today:
            rejected["未来业务日期"] += 1
        else:
            pool.append(r)
    histories = defaultdict(list)
    samples = []
    for r in pool:
        # The entire day is excluded from its own lag window, including other batches.
        previous = [p for p in histories[r["supplier_code"]] if (p.get("metrics_available_date") or p["record_date"]) < r["record_date"] and indicators(p) is not None][-5:]
        if not r.get("costs_confirmed") or r.get("unit_price") is None or r.get("inspected_quantity") != r.get("received_quantity"):
            rejected["成本未确认或未全批检验"] += 1
        elif r.get("lead_time_days") is None:
            rejected["缺少实际交期天数"] += 1
        elif not r.get("accepted_quantity"):
            rejected["零合格交付（单独风险事件）"] += 1
        elif len(previous) < 3:
            rejected["缺少至少3个此前有效批次"] += 1
        else:
            received = r["received_quantity"]
            landed = r["unit_price"]*(1+r["tax_rate"])+r["logistics_cost"]/received
            y = (landed*received+r["rework_cost"]+r["delay_cost"]+r["other_cost"]-r["credit"])/r["accepted_quantity"]
            x = [landed, r["lead_time_days"], *np.median([indicators(p) for p in previous], axis=0).tolist()]
            if not np.isfinite([*x, y]).all() or y < 0:
                rejected["非有限或负成本"] += 1
            else:
                samples.append({"id": r.get("id", r["external_id"]), "batch": r["external_id"], "date": r["record_date"], "supplier": r["supplier_code"], "x": x, "y": y, "demo": r.get("is_demo", False)})
        histories[r["supplier_code"]].append(r)
    return samples, dict(rejected), pool


def fit(x, y, alpha):
    # Fit all preprocessing on training rows only. Keep target losses untouched.
    lo, hi = np.quantile(x, [.01, .99], axis=0)
    clipped = np.clip(x, lo, hi)
    mu, scale = clipped.mean(axis=0), clipped.std(axis=0)
    scale = np.where(scale < 1e-10, 1, scale)
    z = (clipped-mu)/scale
    center = float(np.mean(y))
    beta = np.linalg.solve(z.T@z+alpha*np.eye(x.shape[1]), z.T@(y-center))
    return {"lo": lo, "hi": hi, "mean": mu, "scale": scale, "beta": beta, "center": center, "alpha": alpha}


def predict(model, x):
    return model["center"]+((np.clip(x, model["lo"], model["hi"])-model["mean"])/model["scale"])@model["beta"]


def evaluate(actual, predicted):
    error = actual-predicted
    total = float(np.sum((actual-np.mean(actual))**2))
    return {"mae": float(np.mean(abs(error))), "rmse": float(np.sqrt(np.mean(error**2))), "r_squared": 1-float(np.sum(error**2))/total if total > 1e-12 else None}


def build_model(rows, currency, unit):
    samples, rejected, pool = prepare(rows, currency, unit)
    result = {"version": VERSION, "status": "insufficient", "usable": False, "n": len(samples), "raw_n": len(rows), "rejected": rejected, "features": [{"key": k, "label": label, "rule": rule, "unit": u} for k, label, rule, u in FEATURES], "warnings": [], "weights": [], "samples": [], "demo_count": sum(s["demo"] for s in samples)}
    signature = json.dumps(samples, sort_keys=True, ensure_ascii=False)
    result["fingerprint"] = hashlib.sha256((VERSION+currency+unit+signature).encode()).hexdigest()[:20]
    dates = sorted({s["date"] for s in samples})
    if len(samples) < 60 or len(dates) < 10:
        result["warnings"] = ["至少60个可建模批次、10个不同业务日期；各供应商需有此前至少3批完整指标。该门槛为系统上线规则，不代表样本必然充分。"]
        return result
    cutoff = dates[max(1, int(len(dates)*.8))]
    train = [s for s in samples if s["date"] < cutoff]
    test = [s for s in samples if s["date"] >= cutoff]
    if len(train) < 40 or len(test) < 10:
        result["warnings"] = ["按日期切分后训练集至少40条、留出集至少10条。"]
        return result
    x, y = np.array([s["x"] for s in train]), np.array([s["y"] for s in train])
    xt, yt = np.array([s["x"] for s in test]), np.array([s["y"] for s in test])
    constant = np.std(x, axis=0) < 1e-10
    if constant.any():
        result["warnings"].append("训练集恒定指标无法识别独立系数："+"、".join(FEATURES[i][1] for i in np.flatnonzero(constant)))
    # Nested rolling-date validation chooses regularization without looking at holdout.
    train_dates = sorted({s["date"] for s in train})
    scores = []
    for alpha in [.1, 1., 10., 100.]:
        errors = []
        for fraction in [.5, .65, .8]:
            boundary = train_dates[int(len(train_dates)*fraction)]
            mask = np.array([s["date"] < boundary for s in train])
            if mask.sum() >= 15 and (~mask).sum() >= 5:
                errors.append(evaluate(y[~mask], predict(fit(x[mask], y[mask], alpha), x[~mask]))["mae"])
        scores.append({"alpha": alpha, "mae": float(np.mean(errors))})
    alpha = min(scores, key=lambda s: s["mae"])["alpha"]
    model = fit(x, y, alpha)
    yp = predict(model, xt)
    validation = evaluate(yt, yp)
    baseline = evaluate(yt, np.full(len(yt), np.median(y)))
    validation.update(train_n=len(train), test_n=len(test), cutoff=cutoff, baseline_mae=baseline["mae"], alpha=alpha, tuning=scores)
    b = model["beta"]
    magnitude = abs(b)
    weights = magnitude/magnitude.sum() if magnitude.sum() > 1e-12 else np.zeros(len(FEATURES))
    centered = x-x.mean(axis=0)
    norms = np.sqrt((centered**2).sum(axis=0))
    corr = (centered.T@centered)/np.maximum(np.outer(norms, norms), 1e-20)
    correlated = [(i, j) for i in range(len(FEATURES)) for j in range(i+1, len(FEATURES)) if abs(corr[i, j]) >= .9]
    if correlated:
        result["warnings"].append("强共线性使单项权重不稳定："+"；".join(FEATURES[i][1]+" / "+FEATURES[j][1] for i, j in correlated))
    rng = np.random.default_rng(20260905)
    bootstrap = []
    for _ in range(60):
        selected = rng.choice(train_dates, len(train_dates), replace=True)
        indices = np.concatenate([np.flatnonzero(np.array([s["date"] == d for s in train])) for d in selected])
        boot = abs(fit(x[indices], y[indices], alpha)["beta"])
        if boot.sum() > 1e-12:
            bootstrap.append(boot/boot.sum())
    ci = np.quantile(bootstrap, [.025, .975], axis=0) if bootstrap else np.zeros((2, 5))
    raw_beta = b/model["scale"]
    result.update(status="review", validation=validation, intercept=float(model["center"]-model["mean"]@raw_beta), correlation=corr.tolist(), model={k: v.tolist() if isinstance(v, np.ndarray) else v for k, v in model.items()})
    for j, (key, label, rule, u) in enumerate(FEATURES):
        changes = []
        for _ in range(20):
            shuffled = xt.copy(); shuffled[:, j] = rng.permutation(shuffled[:, j])
            changes.append(evaluate(yt, predict(model, shuffled))["mae"]-validation["mae"])
        result["weights"].append({"key": key, "label": label, "rule": rule, "unit": u, "coefficient": float(raw_beta[j]), "standardized": float(b[j]), "weight": float(weights[j]), "ci_low": float(ci[0, j]), "ci_high": float(ci[1, j]), "permutation_mae": float(np.mean(changes)), "mean": float(model["mean"][j]), "std": float(model["scale"][j]), "min": float(model["lo"][j]), "max": float(model["hi"][j]), "constant": bool(constant[j])})
    result["weight_sum"] = float(weights.sum())
    result["samples"] = [{**s, "prediction": float(pred), "residual": float(s["y"]-pred), "split": "验证"} for s, pred in zip(test, yp, strict=True)]
    residual = yt-yp
    result["residual_diagnostics"] = {"mean": float(residual.mean()), "std": float(residual.std()), "shapiro_p": float(stats.shapiro(residual[:5000]).pvalue) if np.std(residual) > 1e-12 else None, "qq": [list(map(float, pair)) for pair in zip(*stats.probplot(residual, fit=False), strict=True)]}
    result["outlier_rows"] = int(np.any((x < model["lo"]) | (x > model["hi"]), axis=1).sum())
    result["curves"] = []
    for j, (_, label, _, _) in enumerate(FEATURES):
        grid = np.tile(model["mean"], (30, 1))
        grid[:, j] = np.linspace(model["lo"][j], model["hi"][j], 30)
        result["curves"].append({"name": label, "data": [[float(a), float(v)] for a, v in zip(grid[:, j], predict(model, grid), strict=True)]})
    result["usable"] = bool(not constant.any() and not correlated and validation["mae"] < baseline["mae"] and validation["r_squared"] is not None and validation["r_squared"] > 0 and np.all(yp >= 0) and magnitude.sum() > 1e-12)
    result["missing_availability"] = sum(not r.get("metrics_available_date") for r in pool)
    if result["missing_availability"]:
        result["usable"] = False
        result["warnings"].append("缺少指标实际可用日期，当前只能按业务日期诊断，不能回归预测定标。请补充 metrics_available_date。")
    if validation["mae"] >= baseline["mae"] or validation["r_squared"] is None or validation["r_squared"] <= 0:
        result["warnings"].append("时间留出验证未优于基线或R²≤0，不用于回归定标。")
    if result["demo_count"]:
        result["warnings"].append("包含模拟数据，只能演示，禁止正式定标。")
    result["status"] = "validated" if result["usable"] else "review"
    result["latest_profiles"] = {}
    for supplier in {r["supplier_code"] for r in pool}:
        history = [r for r in pool if r["supplier_code"] == supplier and (r.get("metrics_available_date") or r["record_date"]) <= datetime.now(UTC).date().isoformat() and indicators(r) is not None][-5:]
        if len(history) >= 3:
            result["latest_profiles"][supplier] = {"values": np.median([indicators(r) for r in history], axis=0).tolist(), "zero_yield": any(r.get("accepted_quantity") == 0 for r in history)}
    return result


def quote_prediction(result, supplier_code, landed_price, quantity, lead_time_days=None):
    profile = result.get("latest_profiles", {}).get(supplier_code)
    if not result.get("pricing_usable") or not profile or profile["zero_yield"]:
        return {"total": None, "reason": "模型或DOE多因子交叉验证未通过、历史不足或近期有零合格交付"}
    if lead_time_days is None:
        return {"total": None, "reason": "报价缺少承诺交期，禁止使用多元定价系数"}
    x = np.array([landed_price, lead_time_days, *profile["values"]])
    model = {k: np.array(v) if isinstance(v, list) else v for k, v in result["model"].items()}
    if np.any(x < model["lo"]) or np.any(x > model["hi"]):
        return {"total": None, "reason": "报价或历史指标超出训练适用范围，禁止外推"}
    value = float(predict(model, x))
    if value < 0:
        return {"total": None, "reason": "预测负成本，需复核"}
    return {"total": value*quantity, "unit_cost": value, "reason": "按时间验证的多元模型", "contributions": (model["beta"]*(x-model["mean"])/model["scale"]).tolist()}
