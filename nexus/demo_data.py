"""Synthetic telemetry generator - two customer tenants, ten applications.

ACME RETAIL (acme):
  - web-gateway          healthy baseline (upstream 503s from checkout)
  - checkout-api         ACTIVE SEV1: DB pool exhaustion after deploy v6.14.2
  - payment-api          PREDICTIVE: slow JVM heap leak
  - fulfillment-worker   PREDICTIVE: Kafka queue backlog building
  - inventory-svc        healthy
  - search-svc           healthy

GLOBEX FINANCIAL (globex):
  - trading-api          ACTIVE SEV2: latency spike from market-data feed timeouts
  - ledger-svc           healthy
  - risk-engine          error-pattern anomaly (VaR calc failures)
  - notification-svc     WARN: stuck delivery jobs

All state is in-memory and regenerable via reset(); logs also persist to PostgreSQL.
"""
from __future__ import annotations

import random
import time

TENANTS = [
    {"slug": "acme", "name": "Acme Retail", "industry": "E-commerce"},
    {"slug": "globex", "name": "Globex Financial", "industry": "Capital Markets"},
]

SERVICE_META = {
    # --- acme ---
    "web-gateway":        {"tenant": "acme", "owner": "Edge Platform Team", "oncall": "edge-oncall@acme.com", "criticality": "high"},
    "checkout-api":       {"tenant": "acme", "owner": "Commerce Team", "oncall": "commerce-oncall@acme.com", "criticality": "critical"},
    "payment-api":        {"tenant": "acme", "owner": "Payments Team", "oncall": "payments-oncall@acme.com", "criticality": "critical"},
    "fulfillment-worker": {"tenant": "acme", "owner": "Order Ops Team", "oncall": "orderops-oncall@acme.com", "criticality": "medium"},
    "inventory-svc":      {"tenant": "acme", "owner": "Commerce Team", "oncall": "commerce-oncall@acme.com", "criticality": "high"},
    "search-svc":         {"tenant": "acme", "owner": "Discovery Team", "oncall": "discovery-oncall@acme.com", "criticality": "medium"},
    # --- globex ---
    "trading-api":        {"tenant": "globex", "owner": "Trading Platform", "oncall": "trading-oncall@globex.com", "criticality": "critical"},
    "ledger-svc":         {"tenant": "globex", "owner": "Core Banking", "oncall": "ledger-oncall@globex.com", "criticality": "critical"},
    "risk-engine":        {"tenant": "globex", "owner": "Risk Technology", "oncall": "risk-oncall@globex.com", "criticality": "high"},
    "notification-svc":   {"tenant": "globex", "owner": "Client Services", "oncall": "clients-oncall@globex.com", "criticality": "medium"},
}

SERVICES = list(SERVICE_META)

APPLICATIONS = [
    # tenant, app name, owner, oncall, criticality, description, [services]
    ("acme", "Storefront Edge", "Edge Platform Team", "edge-oncall@acme.com", "high",
     "Public web/API gateway for all storefront traffic", ["web-gateway"]),
    ("acme", "Checkout", "Commerce Team", "commerce-oncall@acme.com", "critical",
     "Order capture, validation and persistence", ["checkout-api"]),
    ("acme", "Payments", "Payments Team", "payments-oncall@acme.com", "critical",
     "Payment authorization via external PSPs", ["payment-api"]),
    ("acme", "Fulfillment", "Order Ops Team", "orderops-oncall@acme.com", "medium",
     "Async order fulfillment pipeline on Kafka", ["fulfillment-worker"]),
    ("acme", "Inventory", "Commerce Team", "commerce-oncall@acme.com", "high",
     "Stock levels and reservations", ["inventory-svc"]),
    ("acme", "Search & Discovery", "Discovery Team", "discovery-oncall@acme.com", "medium",
     "Product search and recommendations", ["search-svc"]),
    ("globex", "Trading Gateway", "Trading Platform", "trading-oncall@globex.com", "critical",
     "Order routing and execution against market venues", ["trading-api"]),
    ("globex", "General Ledger", "Core Banking", "ledger-oncall@globex.com", "critical",
     "Double-entry ledger of record", ["ledger-svc"]),
    ("globex", "Risk Engine", "Risk Technology", "risk-oncall@globex.com", "high",
     "Intraday VaR and exposure calculation", ["risk-engine"]),
    ("globex", "Client Notifications", "Client Services", "clients-oncall@globex.com", "medium",
     "Trade confirmations and client alerting", ["notification-svc"]),
]

TOPOLOGY = {
    "web-gateway": ["checkout-api", "search-svc"],
    "checkout-api": ["payment-api", "inventory-svc", "postgres-main", "redis-cache", "kafka"],
    "payment-api": ["external-psp", "postgres-payments"],
    "fulfillment-worker": ["kafka", "order-db"],
    "inventory-svc": ["postgres-main", "redis-cache"],
    "search-svc": ["elasticsearch"],
    "trading-api": ["market-data-feed", "ledger-svc", "kafka-gx"],
    "ledger-svc": ["postgres-ledger"],
    "risk-engine": ["market-data-feed", "postgres-risk"],
    "notification-svc": ["kafka-gx", "smtp-relay"],
}

POINTS = 60
STEP = 60


class World:
    def __init__(self):
        self.reset()

    def reset(self):
        self.now = time.time()
        self.metrics: dict[str, dict[str, list[tuple[float, float]]]] = {}
        self.logs: list[dict] = []
        self.changes: list[dict] = []
        self._gen_metrics()
        self._gen_logs()
        self._gen_changes()

    # ---------------- metrics ----------------
    def _series(self, base, noise, ramp_from=None, ramp_to=None, ramp_start=0.5, cap=None):
        pts = []
        for i in range(POINTS):
            ts = self.now - (POINTS - 1 - i) * STEP
            v = base + random.uniform(-noise, noise)
            if ramp_from is not None:
                frac = i / (POINTS - 1)
                if frac >= ramp_start:
                    p = (frac - ramp_start) / (1 - ramp_start)
                    v = ramp_from + (ramp_to - ramp_from) * p + random.uniform(-noise, noise)
            v = max(v, 0)
            if cap is not None:
                v = min(v, cap)
            pts.append((ts, round(v, 2)))
        return pts

    def _baseline(self, latency=220, pool=40, heap=55, queue=150, err=0.4):
        return {
            "latency_p99_ms": self._series(latency, latency * 0.1),
            "db_pool_utilization": self._series(pool, 4, cap=100),
            "heap_used_pct": self._series(heap, 4, cap=100),
            "queue_depth": self._series(queue, queue * 0.3),
            "error_rate_pct": self._series(err, 0.2),
        }

    def _gen_metrics(self):
        m = {}
        # ---- acme ----
        m["web-gateway"] = self._baseline(latency=210, pool=35)
        m["checkout-api"] = {
            "db_pool_utilization": self._series(60, 3, ramp_from=62, ramp_to=99, ramp_start=0.58, cap=100),
            "latency_p99_ms": self._series(180, 20, ramp_from=200, ramp_to=2400, ramp_start=0.60),
            "error_rate_pct": self._series(0.5, 0.2, ramp_from=0.6, ramp_to=7.8, ramp_start=0.62),
            "heap_used_pct": self._series(58, 4, cap=100),
            "queue_depth": self._series(150, 40),
        }
        m["payment-api"] = {**self._baseline(latency=240, pool=48),
                            "heap_used_pct": self._series(55, 1.5, ramp_from=56, ramp_to=78,
                                                          ramp_start=0.15, cap=100)}
        m["fulfillment-worker"] = {**self._baseline(latency=300, heap=61),
                                   "queue_depth": self._series(900, 120, ramp_from=1000,
                                                               ramp_to=4800, ramp_start=0.35)}
        m["inventory-svc"] = self._baseline(latency=140, pool=42, heap=60)
        m["search-svc"] = self._baseline(latency=95, pool=25, heap=52, err=0.3)
        # ---- globex ----
        m["trading-api"] = {
            **self._baseline(latency=45, pool=55, heap=62),
            "latency_p99_ms": self._series(45, 6, ramp_from=50, ramp_to=1900, ramp_start=0.7),
            "error_rate_pct": self._series(0.2, 0.1, ramp_from=0.3, ramp_to=5.6, ramp_start=0.72),
        }
        m["ledger-svc"] = self._baseline(latency=120, pool=50, heap=58)
        m["risk-engine"] = self._baseline(latency=850, pool=45, heap=70)
        m["notification-svc"] = {**self._baseline(latency=180, heap=48),
                                 "queue_depth": self._series(2200, 300)}
        self.metrics = m

    # ---------------- logs ----------------
    def _log(self, minutes_ago, service, level, message):
        self.logs.append({"ts": self.now - minutes_ago * 60, "service": service,
                          "level": level, "message": message})

    def _gen_logs(self):
        rnd = random.Random(42)
        normal = [
            ("web-gateway", "INFO", "Request completed path=/api/products status=200 duration={d}ms"),
            ("web-gateway", "INFO", "Request completed path=/api/cart status=200 duration={d}ms"),
            ("checkout-api", "INFO", "Order {oid} validated for customer {cid}"),
            ("checkout-api", "INFO", "Inventory reserved for order {oid}"),
            ("payment-api", "INFO", "Payment authorized txn={txn} amount={amt} currency=USD"),
            ("fulfillment-worker", "INFO", "Consumed order event {oid} partition={p} offset={o}"),
            ("payment-api", "WARN", "PSP response slow txn={txn} duration={d}ms"),
            ("inventory-svc", "INFO", "Stock level updated sku=SKU{sku} qty={q}"),
            ("search-svc", "INFO", "Query served q_hash={qh} hits={q} duration={d}ms"),
            ("trading-api", "INFO", "Order routed order_id=GX{oid2} venue=NYSE qty={q}"),
            ("ledger-svc", "INFO", "Journal entry posted entry={oid2} debit={amt} credit={amt}"),
            ("risk-engine", "INFO", "VaR batch completed portfolios={q} duration={d}ms"),
            ("notification-svc", "INFO", "Trade confirmation sent client=CL{cid} channel=email"),
        ]
        for _ in range(1100):
            svc, lvl, tpl = rnd.choice(normal)
            self._log(rnd.uniform(0, 58), svc, lvl, tpl.format(
                d=rnd.randint(40, 900), oid=f"ORD-{rnd.randint(100000, 999999)}",
                oid2=rnd.randint(1000000, 9999999),
                cid=f"C{rnd.randint(10000, 99999)}", txn=f"TX{rnd.randint(1000000, 9999999)}",
                amt=round(rnd.uniform(10, 400), 2), p=rnd.randint(0, 11),
                o=rnd.randint(100000, 999999), sku=rnd.randint(10000, 99999),
                q=rnd.randint(1, 500), qh=rnd.randint(100000, 999999)))

        # ---- acme scenario: checkout pool exhaustion after deploy ----
        self._log(26, "checkout-api", "INFO",
                  "Deployment checkout-api v6.14.2 completed successfully (previous: v6.14.1)")
        for _ in range(160):
            mins = rnd.uniform(0, 23) ** 0.7 / (23 ** 0.7) * 23
            self._log(mins, "checkout-api", "ERROR",
                      f"SQLException: timeout acquiring connection from pool HikariPool-1 "
                      f"(waited {rnd.randint(30000, 30050)}ms, active={rnd.randint(48, 50)}, "
                      f"idle=0, waiting={rnd.randint(15, 60)})")
        for _ in range(45):
            self._log(rnd.uniform(0, 20), "checkout-api", "ERROR",
                      f"Order ORD-{rnd.randint(100000, 999999)} failed: could not persist order "
                      f"- connection unavailable")
        for _ in range(30):
            self._log(rnd.uniform(0, 18), "web-gateway", "ERROR",
                      f"Upstream checkout-api returned 503 path=/api/checkout duration={rnd.randint(29000, 31000)}ms")
        for _ in range(20):
            self._log(rnd.uniform(0, 50), "payment-api", "WARN",
                      f"GC overhead rising: old gen at {rnd.randint(68, 79)}% after full GC, "
                      f"pause={rnd.randint(400, 1400)}ms")
        for _ in range(14):
            self._log(rnd.uniform(0, 30), "fulfillment-worker", "WARN",
                      f"Consumer lag growing: partition={rnd.randint(0, 11)} lag={rnd.randint(2000, 5000)}")

        # ---- globex scenario: market-data feed timeouts hitting trading-api ----
        self._log(17, "trading-api", "INFO",
                  "Config change applied: market-data-feed failover endpoint switched to dr-site")
        for _ in range(90):
            mins = rnd.uniform(0, 16)
            self._log(mins, "trading-api", "ERROR",
                      f"MarketDataTimeout: no tick received for symbol batch in {rnd.randint(4900, 5200)}ms "
                      f"(feed=dr-site, retry={rnd.randint(1, 3)})")
        for _ in range(25):
            self._log(rnd.uniform(0, 14), "trading-api", "ERROR",
                      f"Order GX{rnd.randint(1000000, 9999999)} rejected: stale price, "
                      f"quote age {rnd.randint(5100, 9000)}ms exceeds limit 5000ms")
        for _ in range(18):
            self._log(rnd.uniform(0, 40), "risk-engine", "ERROR",
                      f"VaR calculation failed for portfolio P{rnd.randint(100, 999)}: "
                      f"covariance matrix not positive definite after {rnd.randint(2, 5)} retries")
        for _ in range(12):
            self._log(rnd.uniform(0, 45), "notification-svc", "WARN",
                      f"Delivery job JOB-{rnd.randint(10000, 99999)} stuck in RUNNING for "
                      f"{rnd.randint(16, 55)}m, channel=email")

        self.logs.sort(key=lambda x: x["ts"])

    def _gen_changes(self):
        self.changes = [
            {"ts": self.now - 26 * 60, "service": "checkout-api", "type": "deployment",
             "detail": "checkout-api v6.14.2 deployed (PR #4821: parallelize order persistence writes)",
             "author": "commerce-team"},
            {"ts": self.now - 17 * 60, "service": "trading-api", "type": "config",
             "detail": "market-data-feed failover endpoint switched to dr-site (change CHG-2214)",
             "author": "trading-platform"},
            {"ts": self.now - 4 * 3600, "service": "payment-api", "type": "deployment",
             "detail": "payment-api v3.9.0 deployed (new PSP retry logic)", "author": "payments-team"},
            {"ts": self.now - 26 * 3600, "service": "fulfillment-worker", "type": "config",
             "detail": "Kafka consumer fetch.max.bytes lowered during network incident",
             "author": "orderops-team"},
        ]

    # ---------------- remediation effects ----------------
    def resolve_metric(self, service, metric, target):
        series = self.metrics[service][metric]
        n = len(series)
        start_v = series[max(0, n - 8)][1]
        for i in range(n - 6, n):
            frac = (i - (n - 7)) / 6
            ts = series[i][0]
            series[i] = (ts, round(start_v + (target - start_v) * frac, 2))


WORLD = World()
