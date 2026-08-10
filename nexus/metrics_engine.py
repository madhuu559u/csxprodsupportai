"""Use case 2 - Predictive Alerts.

Linear-trend forecasting over recent metric samples: fits a least-squares line,
projects forward, and raises a predictive alert with estimated time-to-breach
and a confidence score (R^2). Deliberately simple and explainable - the
blueprint's guidance is strong baselines before exotic ML.
"""
from __future__ import annotations

import time

FRIENDLY = {
    "db_pool_utilization": ("DB connection pool exhaustion", "%"),
    "heap_used_pct": ("JVM heap exhaustion", "%"),
    "latency_p99_ms": ("API latency breach (p99)", "ms"),
    "queue_depth": ("Queue backlog overflow", "msgs"),
    "error_rate_pct": ("Error-rate breach", "%"),
}


def _linfit(points: list[tuple[float, float]]):
    n = len(points)
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return 0.0, my, 0.0
    slope = sum((x - mx) * (y - my) for x, y in points) / sxx
    intercept = my - slope * mx
    ss_tot = sum((y - my) ** 2 for y in ys) or 1e-9
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in points)
    r2 = max(0.0, 1 - ss_res / ss_tot)
    return slope, intercept, r2


def current_breaches(metrics: dict, thresholds: dict) -> list[dict]:
    """Metrics already past warn/critical right now."""
    out = []
    for service, series_map in metrics.items():
        for metric, series in series_map.items():
            th = thresholds.get(metric)
            if not th:
                continue
            val = series[-1][1]
            level = "critical" if val >= th["critical"] else "warn" if val >= th["warn"] else None
            if level:
                out.append({
                    "service": service, "metric": metric, "value": val,
                    "threshold": th[level], "level": level,
                    "title": FRIENDLY.get(metric, (metric, ""))[0],
                })
    return out


def predictions(metrics: dict, thresholds: dict, lookback: int = 15,
                horizon_min: int = 60, min_conf: float = 0.6) -> list[dict]:
    """Forecast threshold crossings within the horizon for metrics not yet critical."""
    now = time.time()
    out = []
    for service, series_map in metrics.items():
        for metric, series in series_map.items():
            th = thresholds.get(metric)
            if not th:
                continue
            recent = series[-lookback:]
            val = recent[-1][1]
            if val >= th["critical"]:
                continue  # already an active breach, not a prediction
            slope, intercept, r2 = _linfit(recent)
            if slope <= 0 or r2 < min_conf:
                continue
            eta_s = (th["critical"] - (slope * now + intercept)) / slope
            if eta_s < 0 or eta_s > horizon_min * 60:
                continue
            out.append({
                "service": service,
                "metric": metric,
                "title": FRIENDLY.get(metric, (metric, ""))[0],
                "unit": FRIENDLY.get(metric, (metric, ""))[1],
                "current": val,
                "threshold": th["critical"],
                "eta_minutes": round(eta_s / 60),
                "confidence": round(r2, 2),
                "slope_per_min": round(slope * 60, 3),
            })
    out.sort(key=lambda p: p["eta_minutes"])
    return out
