"""
simple_pipeline.py

Features:
1. Ingest data
2. Validate data
3. Transform data
4. Quality checks
5. Save output
6. Prometheus monitoring
7. Unit tests (pytest)

Task coverage:
- Extension C is partially covered with Prometheus counters, a stage
  duration histogram, and a /metrics endpoint on port 8000.
- Extension B is partially covered with basic pytest unit tests for
  validation and transform logic.
- Grafana dashboard JSON, alert rules, Hypothesis tests, pandas testing,
  and pytest-cov coverage reporting are not included in this script.

Run Pipeline:
python simple_pipeline.py

Run Tests:
pytest simple_pipeline.py -v
"""

import logging
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from prometheus_client import Counter, Histogram, start_http_server

# ==================================================
# LOGGING
# ==================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

# ==================================================
# METRICS
# ==================================================

# Prometheus counters track how many times the pipeline runs, how many
# rows are processed, and how many validation failures are found.
PIPELINE_RUNS = Counter(
    "pipeline_runs_total",
    "Total pipeline executions",
)

ROWS_PROCESSED = Counter(
    "rows_processed_total",
    "Total rows processed",
)

VALIDATION_ERRORS = Counter(
    "validation_errors_total",
    "Total validation failures",
)

# Histogram records the runtime for each pipeline stage so Prometheus
# can expose stage duration metrics at /metrics.
STAGE_DURATION = Histogram(
    "stage_duration_seconds",
    "Stage execution duration",
    ["stage"],
)

# ==================================================
# CONFIG
# ==================================================

OUTPUT_DIR = Path("output")
MIN_ROWS = 100

# ==================================================
# INGESTION
# ==================================================


def load_data(rows=1000):
    start = time.time()

    rng = np.random.default_rng(42)

    amounts = rng.normal(
        loc=100,
        scale=30,
        size=rows,
    ).round(2)

    bad_idx = rng.choice(
        rows,
        size=int(rows * 0.01),
        replace=False,
    )

    amounts[bad_idx] = -abs(amounts[bad_idx])

    df = pd.DataFrame(
        {
            "id": range(rows),
            "amount": amounts,
            "category": rng.choice(
                ["A", "B", "C", None],
                rows,
                p=[0.4, 0.3, 0.2, 0.1],
            ),
            "ts": pd.date_range(
                "2024-01-01",
                periods=rows,
                freq="h",
            ),
        }
    )

    STAGE_DURATION.labels(stage="ingestion").observe(time.time() - start)

    return df


# ==================================================
# VALIDATION
# ==================================================


def validate_data(df):
    start = time.time()

    df = df.copy()

    valid_df = df[
        df["id"].notna()
        & df["amount"].notna()
        & (df["amount"] > 0)
    ]

    invalid_rows = len(df) - len(valid_df)

    VALIDATION_ERRORS.inc(invalid_rows)

    STAGE_DURATION.labels(stage="validation").observe(time.time() - start)

    logging.info("Validation complete. Removed %s rows", invalid_rows)

    return valid_df


# ==================================================
# TRANSFORM
# ==================================================


def transform_data(df):
    start = time.time()

    df = df.copy()

    df["category"] = df["category"].fillna("UNKNOWN")

    df["amount_tier"] = pd.cut(
        df["amount"],
        bins=[
            0,
            50,
            100,
            150,
            float("inf"),
        ],
        labels=[
            "low",
            "medium",
            "high",
            "premium",
        ],
    )

    df["date"] = pd.to_datetime(df["ts"]).dt.date
    df["hour"] = pd.to_datetime(df["ts"]).dt.hour

    mean_amt = df["amount"].mean()
    std_amt = df["amount"].std()

    df["amount_zscore"] = ((df["amount"] - mean_amt) / std_amt).round(4)

    STAGE_DURATION.labels(stage="transform").observe(time.time() - start)

    return df


# ==================================================
# QUALITY CHECKS
# ==================================================


def run_quality_checks(df):
    if len(df) < MIN_ROWS:
        raise ValueError("Row count too low")

    if df["amount"].mean() < 80:
        raise ValueError("Amount mean too low")

    if df["amount"].mean() > 120:
        raise ValueError("Amount mean too high")

    logging.info("Quality checks passed")


# ==================================================
# SAVE
# ==================================================


def save_data(df):
    OUTPUT_DIR.mkdir(exist_ok=True)

    output_file = OUTPUT_DIR / f"processed_{date.today()}.csv"

    df.to_csv(
        output_file,
        index=False,
    )

    logging.info("Saved file: %s", output_file)

    return output_file


# ==================================================
# PIPELINE
# ==================================================


def run_pipeline():
    PIPELINE_RUNS.inc()

    logging.info("Pipeline Started")

    raw_df = load_data()

    ROWS_PROCESSED.inc(len(raw_df))

    valid_df = validate_data(raw_df)

    transformed_df = transform_data(valid_df)

    run_quality_checks(transformed_df)

    save_data(transformed_df)

    logging.info("Pipeline Completed")


# ==================================================
# MAIN
# ==================================================


if __name__ == "__main__":
    # Starts the Prometheus metrics endpoint required by Extension C.
    start_http_server(8000)

    print("Prometheus Metrics:")
    print("http://localhost:8000/metrics")

    run_pipeline()


# ==================================================
# PYTEST TESTS
# ==================================================

# These pytest unit tests cover validator and transform behavior from
# Extension B. They are basic examples, not property-based tests.


def test_validation_removes_negative_amount():
    df = pd.DataFrame(
        {
            "id": [1, 2],
            "amount": [100, -10],
            "category": ["A", "B"],
            "ts": [
                "2024-01-01",
                "2024-01-01",
            ],
        }
    )

    result = validate_data(df)

    assert len(result) == 1


def test_unknown_category():
    df = pd.DataFrame(
        {
            "id": [1],
            "amount": [100],
            "category": [None],
            "ts": ["2024-01-01"],
        }
    )

    result = transform_data(df)

    assert result["category"].iloc[0] == "UNKNOWN"


def test_low_tier():
    df = pd.DataFrame(
        {
            "id": [1],
            "amount": [20],
            "category": ["A"],
            "ts": ["2024-01-01"],
        }
    )

    result = transform_data(df)

    assert str(result["amount_tier"].iloc[0]) == "low"


def test_premium_tier():
    df = pd.DataFrame(
        {
            "id": [1],
            "amount": [250],
            "category": ["A"],
            "ts": ["2024-01-01"],
        }
    )

    result = transform_data(df)

    assert str(result["amount_tier"].iloc[0]) == "premium"
