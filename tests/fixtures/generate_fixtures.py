"""
generate_fixtures.py
====================
Generates synthetic but realistic time-series fixture data for the anomaly
detector CI backtest. Run once to regenerate — committed output is used by
the CI workflow so no runtime generation is needed.

Usage: python tests/fixtures/generate_fixtures.py
"""
import csv
import os
import random

import pandas as pd
import numpy as np

random.seed(42)
np.random.seed(42)

OUT_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Build 90-day synthetic ecommerce time series ──────────────────────────────
dates = pd.date_range("2025-10-01", periods=90, freq="D")
n = len(dates)

# Stable base metrics with realistic weekly seasonality (no random walk)
day_of_week = np.array([d.weekday() for d in dates])
weekly_factor = 1.0 + 0.12 * np.sin(2 * np.pi * day_of_week / 7)

# Small independent Gaussian noise (not cumulative)
revenue_base = 5000 * weekly_factor + np.random.normal(0, 80, n)
traffic_base = 1200 * weekly_factor + np.random.normal(0, 30, n)
orders_base  = 80   * weekly_factor + np.random.normal(0, 4,  n)

# Inject 3 known anomaly dates with severe drops (~60%)
ANOMALY_INDICES = [20, 45, 72]
LABELED_DATES = [str(dates[i].date()) for i in ANOMALY_INDICES]

for idx in ANOMALY_INDICES:
    revenue_base[idx] *= 0.38   # ~62% drop — well outside 2-sigma
    traffic_base[idx] *= 0.40
    orders_base[idx]  *= 0.40

revenue_base = np.maximum(revenue_base, 100)
traffic_base = np.maximum(traffic_base, 10)
orders_base  = np.maximum(orders_base,  1)

cvr = orders_base / traffic_base

rows = []
regions = ["North America", "Europe", "Asia"]
devices = ["desktop", "mobile", "tablet"]
sources = ["organic", "paid_search", "email", "direct"]

for i, date in enumerate(dates):
    rows.append({
        "date": str(date.date()),
        "revenue": round(float(revenue_base[i]), 2),
        "traffic": round(float(traffic_base[i]), 0),
        "orders":  round(float(orders_base[i]),  0),
        "conversion_rate": round(float(cvr[i]), 4),
        "region":         regions[i % 3],
        "device":         devices[i % 3],
        "traffic_source": sources[i % 4],
    })

ts_path = os.path.join(OUT_DIR, "sample_timeseries.csv")
with open(ts_path, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
print(f"Written: {ts_path}")

# ── Write labeled incident dates ──────────────────────────────────────────────
labels_path = os.path.join(OUT_DIR, "labeled_incidents.csv")
with open(labels_path, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["date", "description"])
    for d in LABELED_DATES:
        writer.writerow([d, "synthetic anomaly (~62% revenue drop)"])
print(f"Written: {labels_path}")
print(f"Labeled anomaly dates: {LABELED_DATES}")
