# MetricSleuth 

> **AI-powered Root Cause Analysis engine for business metrics.**

MetricSleuth automatically detects anomalies in time-series KPIs (revenue, traffic, conversion rate) and traces them back to their likely root causes using statistical analysis and a rule-based hypothesis engine — all surfaced in an interactive Streamlit dashboard.

---

## Features

| Module | What it does |
|---|---|
| **Data Loader** | Reads & validates CSVs, coerces dates, deduplicates |
| **Preprocessing** | Rolling stats, pct-change, time features, normalisation |
| **Anomaly Detection** | Rolling Z-score detection with configurable threshold |
| **Segmentation Analysis** | Compares anomaly-day vs. baseline per region / device / source |
| **Correlation Analysis** | Pearson r with p-values; strong-correlator identification |
| **Contribution Analysis** | Proportional attribution of metric changes to factors |
| **Hypothesis Engine** | Rule-based ranked hypotheses with confidence scores |
| **Report Generator** | Structured dict + Markdown RCA report (downloadable) |
| **Streamlit Dashboard** | Interactive UI with Plotly charts and one-click RCA |

---

## Project Structure

```
metric-sleuth/
├── data/
│   └── sample_ecommerce.csv      # Sample dataset with planted anomalies
├── src/
│   ├── data_loader.py
│   ├── preprocessing.py
│   ├── anomaly_detection.py
│   ├── segmentation_analysis.py
│   ├── correlation_analysis.py
│   ├── contribution_analysis.py
│   ├── hypothesis_engine.py
│   └── report_generator.py
├── app/
│   └── streamlit_app.py
├── utils/
│   └── config.py
├── requirements.txt
└── README.md
```

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Launch the dashboard

```bash
streamlit run app/streamlit_app.py
```

### 3. Use the sample dataset or upload your own CSV

The dashboard opens in your browser. Use the sidebar to:
- Choose between the built-in sample dataset or upload your own
- Tune the Z-score threshold and rolling window
- Navigate the five analysis tabs

---

## Dataset Format

Your CSV must contain these columns:

| Column | Type | Description |
|---|---|---|
| `date` | `YYYY-MM-DD` | Daily date |
| `revenue` | float | Daily revenue |
| `traffic` | int | Daily site visits |
| `orders` | int | Daily orders placed |
| `conversion_rate` | float | Orders / traffic |
| `region` | string | Geographic region |
| `device` | string | `Desktop`, `Mobile`, `Tablet` |
| `traffic_source` | string | `Organic Search`, `Paid Search`, etc. |

---

## Configuration

All tuneable parameters live in `utils/config.py`:

```python
ANOMALY_Z_THRESHOLD = 2.0       # |Z-score| threshold
ANOMALY_ROLLING_WINDOW = 7      # Rolling window (days)
STRONG_CORRELATION_THRESHOLD = 0.7
SEGMENT_COLUMNS = ["region", "device", "traffic_source"]
```

---

## Running Individual Modules

Each module can be executed standalone for quick testing:

```bash
python src/anomaly_detection.py
python src/segmentation_analysis.py
python src/report_generator.py
```

---

## Tech Stack

- **Python 3.10+**
- `pandas`, `numpy`, `scipy`, `scikit-learn`
- `plotly` — interactive charts
- `streamlit` — dashboard framework

---

## Sample Output

The RCA report includes:
-  Anomaly detection table with Z-scores
-  Segment performance breakdown
-  Correlation matrix heatmap
-  Contribution donut chart
-  Ranked hypotheses with confidence scores
-  Prioritised recommended actions
-  Downloadable Markdown report
