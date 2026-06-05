"""
Day 7 Task 1: Python Pipeline with Validation

This script converts the notebook `python_pipeline_validation.ipynb` into a
regular Python file.

Included notebook features:
1. Pipeline configuration
2. Structured Loguru logging
3. Pluggable CSV and synthetic ingestors
4. Pydantic row-level validation
5. Great Expectations quality suite
6. Composable transform functions
7. Quality gate with alert hook
8. Partitioned Parquet storage
9. Tenacity retry wrapper
10. APScheduler cron scheduling helper
11. Delta Lake storage extension
12. Pytest and Hypothesis test-suite writer
13. Prometheus metrics extension
14. Airflow DAG writer

Run once:
python task_1_simple_pipeline.py

Run with metrics server:
python task_1_simple_pipeline.py --metrics

Write notebook extension files:
python task_1_simple_pipeline.py --write-tests --write-airflow-dag
"""

from __future__ import annotations

import argparse
import atexit
import logging
import sys
import time
from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import reduce
from pathlib import Path
from typing import Callable, Literal, Optional

import numpy as np
import pandas as pd
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger
from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    start_http_server,
)
from pydantic import BaseModel, ValidationError, field_validator
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

try:
    import great_expectations as gx
except ImportError:  # pragma: no cover - dependency is listed in requirements.
    gx = None


# ==================================================
# STRUCTURED LOGGING
# ==================================================

logger.remove()
logger.add(
    sys.stdout,
    level="INFO",
    format="{time:HH:mm:ss} | {level: <8} | {message}",
    colorize=True,
)
logger.add(
    "pipeline.log",
    rotation="10 MB",
    retention="7 days",
    level="DEBUG",
)


# ==================================================
# CONFIG
# ==================================================

@dataclass
class PipelineConfig:
    """Central pipeline configuration."""

    source_path: Path = Path("data/raw")
    output_path: Path = Path("data/processed")
    schedule_cron: str = "0 6 * * *"
    max_retries: int = 3
    batch_size: int = 1_000
    alert_email: str = "ops@example.com"
    pass_rate_threshold: float = 0.95
    null_rate_limit: float = 0.05
    min_rows: int = 100


# ==================================================
# INGESTION
# ==================================================

class BaseIngestor(ABC):
    """All ingestors return a raw DataFrame."""

    @abstractmethod
    def read(self) -> pd.DataFrame:
        """Read or generate the source data."""


class CsvIngestor(BaseIngestor):
    """Reads a CSV file from disk."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def read(self) -> pd.DataFrame:
        df = pd.read_csv(self.path)
        logger.info("Ingested {:,} rows from {}", len(df), self.path)
        return df


class SyntheticIngestor(BaseIngestor):
    """Generates synthetic transaction data for demo and testing."""

    def __init__(self, n: int = 1_000, seed: int = 42):
        self.n = n
        self.seed = seed

    def read(self) -> pd.DataFrame:
        rng = np.random.default_rng(self.seed)
        amounts = rng.normal(100, 30, self.n).round(2)

        bad_count = max(1, int(self.n * 0.01))
        neg_idx = rng.choice(self.n, size=bad_count, replace=False)
        amounts[neg_idx] = -abs(amounts[neg_idx])

        df = pd.DataFrame(
            {
                "id": range(self.n),
                "amount": amounts,
                "category": rng.choice(
                    ["A", "B", "C", None],
                    self.n,
                    p=[0.4, 0.3, 0.2, 0.1],
                ),
                "ts": pd.date_range("2024-01-01", periods=self.n, freq="1h"),
            }
        )

        logger.info("Generated {:,} synthetic rows (seed={})", self.n, self.seed)
        return df


# ==================================================
# PYDANTIC VALIDATION
# ==================================================

class TransactionRecord(BaseModel):
    """Expected schema for each transaction row."""

    id: int
    amount: float
    category: Optional[Literal["A", "B", "C"]]
    ts: datetime

    @field_validator("amount")
    @classmethod
    def amount_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError(f"amount must be positive, got {value:.2f}")
        return value

    @field_validator("id")
    @classmethod
    def id_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError(f"id must be non-negative, got {value}")
        return value


def validate_batch(
    df: pd.DataFrame,
    pass_threshold: float = 0.95,
) -> tuple[pd.DataFrame, list[dict]]:
    """Validate every row against TransactionRecord."""
    if len(df) == 0:
        return pd.DataFrame(columns=df.columns), []

    valid_rows = []
    errors = []

    for row in df.to_dict("records"):
        try:
            parsed = TransactionRecord(**row)
            valid_rows.append(parsed.model_dump())
        except ValidationError as exc:
            for error in exc.errors():
                errors.append(
                    {
                        "row_id": row.get("id"),
                        "field": error["loc"][0] if error["loc"] else "unknown",
                        "message": error["msg"],
                    }
                )

    pass_rate = len(valid_rows) / len(df)
    logger.info(
        "Validation: {:,} valid | {:,} errors | {:.1f}% pass rate",
        len(valid_rows),
        len(errors),
        pass_rate * 100,
    )

    if pass_rate < pass_threshold:
        logger.warning(
            "Pass rate {:.1f}% is below threshold {:.0f}%",
            pass_rate * 100,
            pass_threshold * 100,
        )

    valid_df = pd.DataFrame(valid_rows) if valid_rows else pd.DataFrame(columns=df.columns)
    return valid_df, errors


# ==================================================
# GREAT EXPECTATIONS QUALITY SUITE
# ==================================================

def build_ge_suite(df: pd.DataFrame) -> dict:
    """Run a Great Expectations expectation suite against a DataFrame."""
    if gx is None:
        raise ImportError("Install great-expectations to run the GE quality suite.")

    context = gx.get_context(mode="ephemeral")
    data_source = context.data_sources.add_pandas("pandas_source")
    data_asset = data_source.add_dataframe_asset("transactions")
    batch_definition = data_asset.add_batch_definition_whole_dataframe("full_batch")
    batch = batch_definition.get_batch(batch_parameters={"dataframe": df})

    suite = context.suites.add(gx.ExpectationSuite(name="txn_suite"))
    suite.add_expectation(gx.expectations.ExpectColumnToExist(column="amount"))
    suite.add_expectation(gx.expectations.ExpectColumnToExist(column="id"))
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToBeBetween(
            column="amount",
            min_value=0,
            max_value=300,
        )
    )
    suite.add_expectation(gx.expectations.ExpectColumnValuesToNotBeNull(column="id"))
    suite.add_expectation(gx.expectations.ExpectColumnValuesToNotBeNull(column="ts"))
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToBeInSet(
            column="category",
            value_set=["A", "B", "C"],
            mostly=0.90,
        )
    )
    suite.add_expectation(gx.expectations.ExpectColumnValuesToBeUnique(column="id"))

    validation_definition = context.run_validation_definition(
        gx.ValidationDefinition(name="txn_vd", data=batch, suite=suite)
    )
    results = validation_definition.run()
    stats = results.statistics

    logger.info(
        "GE suite: {}/{} expectations passed",
        stats["successful_expectations"],
        stats["evaluated_expectations"],
    )

    if not results.success:
        failed = [
            result.expectation_config.type
            for result in results.results
            if not result.success
        ]
        logger.warning("Failed expectations: {}", failed)

    return {
        "success": results.success,
        "passed": stats["successful_expectations"],
        "evaluated": stats["evaluated_expectations"],
    }


# ==================================================
# TRANSFORMS
# ==================================================

TransformFn = Callable[[pd.DataFrame], pd.DataFrame]


def fill_category(df: pd.DataFrame) -> pd.DataFrame:
    """Replace null categories with UNKNOWN."""
    return df.assign(category=df["category"].fillna("UNKNOWN"))


def add_amount_tier(df: pd.DataFrame) -> pd.DataFrame:
    """Bin amount into low, medium, high, and premium tiers."""
    bins = [0, 50, 100, 150, float("inf")]
    labels = ["low", "medium", "high", "premium"]
    return df.assign(
        tier=pd.cut(df["amount"], bins=bins, labels=labels).astype(str)
    )


def extract_date_parts(df: pd.DataFrame) -> pd.DataFrame:
    """Extract date, hour, and day of week from the timestamp."""
    ts = pd.to_datetime(df["ts"])
    return df.assign(
        date=ts.dt.date,
        hour=ts.dt.hour,
        day_of_week=ts.dt.day_name(),
    )


def normalize_amount(df: pd.DataFrame) -> pd.DataFrame:
    """Z-score normalize the amount column."""
    sigma = df["amount"].std()
    if sigma == 0 or pd.isna(sigma):
        return df.assign(amount_z=0.0)

    mean_amount = df["amount"].mean()
    return df.assign(amount_z=((df["amount"] - mean_amount) / sigma).round(4))


def drop_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """Remove duplicate IDs, keeping the first row."""
    before = len(df)
    result = df.drop_duplicates(subset=["id"], keep="first")
    dropped = before - len(result)
    if dropped:
        logger.warning("Dropped {} duplicate rows", dropped)
    return result


def apply_transforms(df: pd.DataFrame, *functions: TransformFn) -> pd.DataFrame:
    """Apply transform functions from left to right."""
    return reduce(lambda current, function: function(current), functions, df)


# ==================================================
# QUALITY GATE
# ==================================================

@dataclass
class QualityCheck:
    name: str
    passed: bool
    value: float
    threshold: float
    description: str = ""

    def __str__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return (
            f"{status:4} {self.name:<20} "
            f"value={self.value:.4f} threshold={self.threshold}"
        )


def send_alert(to: str, subject: str, body: str) -> None:
    """Alert dispatcher placeholder for email, Slack, or PagerDuty."""
    logger.warning("ALERT -> {} | {} | {}", to, subject, body)


def run_quality_gate(df: pd.DataFrame, cfg: PipelineConfig) -> list[QualityCheck]:
    """Run quality checks and raise RuntimeError on any failure."""
    checks = [
        QualityCheck(
            name="null_rate",
            passed=df.isnull().mean().max() < cfg.null_rate_limit,
            value=float(df.isnull().mean().max()),
            threshold=cfg.null_rate_limit,
            description="Max null rate across all columns",
        ),
        QualityCheck(
            name="row_count",
            passed=len(df) >= cfg.min_rows,
            value=float(len(df)),
            threshold=float(cfg.min_rows),
            description="Minimum row count",
        ),
        QualityCheck(
            name="amount_mean",
            passed=80 <= df["amount"].mean() <= 120,
            value=float(df["amount"].mean()),
            threshold=100.0,
            description="Amount mean within expected range [80, 120]",
        ),
        QualityCheck(
            name="dup_id_rate",
            passed=float(df["id"].duplicated().mean()) < 0.01,
            value=float(df["id"].duplicated().mean()),
            threshold=0.01,
            description="Duplicate ID rate below 1%",
        ),
        QualityCheck(
            name="amount_z_range",
            passed=float(df["amount_z"].abs().max()) < 5.0,
            value=float(df["amount_z"].abs().max()),
            threshold=5.0,
            description="No extreme outliers",
        ),
    ]

    logger.info("Quality Gate Results:")
    for check in checks:
        if check.passed:
            logger.info(str(check))
        else:
            logger.error(str(check))

    failures = [check for check in checks if not check.passed]
    if failures:
        names = [failure.name for failure in failures]
        message = f"Quality gate FAILED on: {names}"
        send_alert(cfg.alert_email, "Pipeline Quality Gate Failure", message)
        raise RuntimeError(message)

    logger.info("Quality gate PASSED")
    return checks


# ==================================================
# STORAGE
# ==================================================

def store_parquet(df: pd.DataFrame, cfg: PipelineConfig) -> Path:
    """Write DataFrame to a date-partitioned Parquet file."""
    today = date.today().isoformat()
    partition_dir = cfg.output_path / f"date={today}"
    partition_dir.mkdir(parents=True, exist_ok=True)

    output_path = partition_dir / "data.parquet"
    df.to_parquet(output_path, index=False, compression="snappy")

    size_kb = output_path.stat().st_size / 1024
    logger.info("Stored {:,} rows -> {} ({:.1f} KB)", len(df), output_path, size_kb)
    return output_path


# ==================================================
# END-TO-END PIPELINE WITH RETRY
# ==================================================

_std_logger = logging.getLogger("pipeline")


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=60),
    retry=retry_if_exception_type((IOError, ConnectionError)),
    before_sleep=before_sleep_log(_std_logger, logging.WARNING),
    reraise=True,
)
def run_pipeline(cfg: PipelineConfig, use_ge: bool = True) -> dict:
    """Execute the full ETL pipeline."""
    logger.info("=" * 50)
    logger.info("Pipeline run STARTED")
    logger.info("=" * 50)

    try:
        raw = SyntheticIngestor(n=cfg.batch_size).read()
        valid, errors = validate_batch(raw, cfg.pass_rate_threshold)

        ge_results = {"success": True, "passed": 0, "evaluated": 0}
        if use_ge:
            ge_results = build_ge_suite(valid)
            if not ge_results["success"]:
                raise RuntimeError("Great Expectations suite failed")

        processed = apply_transforms(
            valid,
            drop_duplicates,
            fill_category,
            add_amount_tier,
            extract_date_parts,
            normalize_amount,
        )
        run_quality_gate(processed, cfg)
        output_path = store_parquet(processed, cfg)

        readback = pd.read_parquet(output_path)
        if len(readback) != len(processed):
            raise RuntimeError("Row count mismatch on Parquet readback")

        stats = {
            "status": "success",
            "raw_rows": len(raw),
            "valid_rows": len(valid),
            "validation_errors": len(errors),
            "ge_success": ge_results["success"],
            "output_path": str(output_path),
        }
        logger.info("Pipeline run SUCCEEDED")
        logger.info("Stats: {}", stats)
        return stats
    except Exception as exc:
        logger.error("Pipeline FAILED: {}", exc)
        send_alert(cfg.alert_email, "Pipeline Failure", str(exc))
        raise


# ==================================================
# APSCHEDULER EXTENSION
# ==================================================

def start_scheduler(cfg: PipelineConfig, use_ge: bool = True) -> BackgroundScheduler:
    """Start a background scheduler using the configured cron expression."""
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        run_pipeline,
        trigger=CronTrigger.from_crontab(cfg.schedule_cron),
        kwargs={"cfg": cfg, "use_ge": use_ge},
        id="daily_pipeline",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
        replace_existing=True,
    )
    atexit.register(lambda: scheduler.shutdown(wait=False))
    scheduler.start()

    logger.info("Scheduler started | {} job(s) registered", len(scheduler.get_jobs()))
    for job in scheduler.get_jobs():
        logger.info("Job '{}' | next run: {}", job.id, job.next_run_time)

    return scheduler


def stop_scheduler(scheduler: BackgroundScheduler) -> None:
    """Stop the scheduler cleanly."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped cleanly")
    else:
        logger.info("Scheduler was not running")


# ==================================================
# DELTA LAKE EXTENSION
# ==================================================

DELTA_PATH = "data/delta/transactions"


def store_delta(df: pd.DataFrame, path: str = DELTA_PATH, mode: str = "append") -> None:
    """Write a DataFrame to a Delta Lake table."""
    from deltalake.writer import write_deltalake

    delta_df = df.copy()
    delta_df["date"] = delta_df["date"].astype(str)
    write_deltalake(
        path,
        delta_df,
        mode=mode,
        partition_by=["date"],
        schema_mode="merge",
    )
    logger.info("Delta write: {:,} rows -> {} (mode={})", len(delta_df), path, mode)


def optimize_delta(path: str = DELTA_PATH) -> None:
    """Compact small files and remove old Delta table versions."""
    from deltalake import DeltaTable

    table = DeltaTable(path)
    table.optimize.compact()
    table.vacuum(
        retention_hours=168,
        dry_run=False,
        enforce_retention_duration=False,
    )
    logger.info("Delta optimize + vacuum complete for {}", path)


def time_travel(path: str = DELTA_PATH, version: int = 0) -> pd.DataFrame:
    """Read a historical Delta table version."""
    from deltalake import DeltaTable

    table = DeltaTable(path, version=version)
    df = table.to_pandas()
    logger.info("Time travel: loaded version {} ({:,} rows)", version, len(df))
    return df


# ==================================================
# PROMETHEUS EXTENSION
# ==================================================

registry = CollectorRegistry()

PIPELINE_RUNS_TOTAL = Counter(
    "pipeline_runs_total",
    "Total pipeline run attempts",
    ["status"],
    registry=registry,
)

ROWS_INGESTED = Counter(
    "pipeline_rows_ingested_total",
    "Total rows ingested",
    registry=registry,
)

ROWS_VALID = Counter(
    "pipeline_rows_valid_total",
    "Total rows passing Pydantic validation",
    registry=registry,
)

PROM_VALIDATION_ERRORS = Counter(
    "pipeline_validation_errors_total",
    "Total row-level validation errors",
    registry=registry,
)

STAGE_DURATION = Histogram(
    "pipeline_stage_duration_seconds",
    "Duration of each pipeline stage",
    ["stage"],
    buckets=[0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0],
    registry=registry,
)

LAST_RUN_TIMESTAMP = Gauge(
    "pipeline_last_run_timestamp_seconds",
    "Unix timestamp of the most recent successful run",
    registry=registry,
)

QUALITY_PASS_RATE = Gauge(
    "pipeline_quality_pass_rate",
    "Fraction of rows passing Pydantic validation in latest run",
    registry=registry,
)


@contextmanager
def timed_stage(name: str):
    """Time a pipeline stage and record it to Prometheus."""
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        STAGE_DURATION.labels(stage=name).observe(elapsed)
        logger.info("Stage '{}' took {:.3f}s", name, elapsed)


def run_pipeline_instrumented(cfg: PipelineConfig, use_ge: bool = True) -> dict:
    """Instrumented pipeline run that records Prometheus metrics."""
    try:
        with timed_stage("ingest"):
            raw = SyntheticIngestor(n=cfg.batch_size).read()
            ROWS_INGESTED.inc(len(raw))

        with timed_stage("validate"):
            valid, errors = validate_batch(raw, cfg.pass_rate_threshold)
            ROWS_VALID.inc(len(valid))
            PROM_VALIDATION_ERRORS.inc(len(errors))
            QUALITY_PASS_RATE.set(len(valid) / len(raw))

        with timed_stage("great_expectations"):
            if use_ge:
                ge_results = build_ge_suite(valid)
                if not ge_results["success"]:
                    raise RuntimeError("Great Expectations suite failed")

        with timed_stage("transform"):
            processed = apply_transforms(
                valid,
                drop_duplicates,
                fill_category,
                add_amount_tier,
                extract_date_parts,
                normalize_amount,
            )

        with timed_stage("quality_gate"):
            run_quality_gate(processed, cfg)

        with timed_stage("store"):
            output_path = store_parquet(processed, cfg)

        PIPELINE_RUNS_TOTAL.labels(status="success").inc()
        LAST_RUN_TIMESTAMP.set(time.time())
        return {"status": "success", "output": str(output_path)}
    except Exception:
        PIPELINE_RUNS_TOTAL.labels(status="failure").inc()
        raise


def print_current_metrics() -> None:
    """Print current Prometheus metric values."""
    output = generate_latest(registry).decode()
    for line in output.splitlines():
        if line.strip() and not line.startswith("#"):
            print(line)


# ==================================================
# EXTENSION B TEST-SUITE WRITER
# ==================================================

TEST_PIPELINE_CODE = r'''
import pytest
import pandas as pd
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from task_1_simple_pipeline import (
    add_amount_tier,
    apply_transforms,
    fill_category,
    normalize_amount,
)


class TestFillCategory:
    def test_fills_nulls(self):
        df = pd.DataFrame({"category": ["A", None, "B", None]})
        result = fill_category(df)
        assert result["category"].isnull().sum() == 0
        assert (result["category"] == "UNKNOWN").sum() == 2

    def test_preserves_existing(self):
        df = pd.DataFrame({"category": ["A", "B", "C"]})
        result = fill_category(df)
        assert list(result["category"]) == ["A", "B", "C"]

    def test_empty_dataframe(self):
        df = pd.DataFrame({"category": pd.Series([], dtype=object)})
        result = fill_category(df)
        assert len(result) == 0


class TestAmountTier:
    @pytest.mark.parametrize(
        "amount,expected",
        [
            (25.0, "low"),
            (75.0, "medium"),
            (125.0, "high"),
            (200.0, "premium"),
        ],
    )
    def test_tier_boundaries(self, amount, expected):
        df = pd.DataFrame({"amount": [amount]})
        result = add_amount_tier(df)
        assert result["tier"].iloc[0] == expected

    def test_adds_tier_column(self):
        df = pd.DataFrame({"amount": [10, 60, 110, 160]})
        result = add_amount_tier(df)
        assert "tier" in result.columns
        assert set(result["tier"]) == {"low", "medium", "high", "premium"}


class TestNormalizeAmount:
    def test_z_score_mean_zero(self):
        df = pd.DataFrame({"amount": [10.0, 20.0, 30.0, 40.0, 50.0]})
        result = normalize_amount(df)
        assert abs(result["amount_z"].mean()) < 1e-6

    def test_z_score_std_one(self):
        df = pd.DataFrame({"amount": [10.0, 20.0, 30.0, 40.0, 50.0]})
        result = normalize_amount(df)
        assert abs(result["amount_z"].std() - 1.0) < 0.01


class TestApplyTransforms:
    def test_composes_correctly(self):
        df = pd.DataFrame({"amount": [10.0, 90.0], "category": [None, "A"]})
        result = apply_transforms(df, fill_category, add_amount_tier)
        assert "tier" in result.columns
        assert result["category"].isnull().sum() == 0

    def test_identity_with_no_fns(self):
        df = pd.DataFrame({"x": [1, 2, 3]})
        result = apply_transforms(df)
        pd.testing.assert_frame_equal(result, df)


valid_amounts = st.floats(min_value=0.01, max_value=299.0, allow_nan=False)
categories = st.one_of(st.just("A"), st.just("B"), st.just("C"), st.none())


@given(amounts=st.lists(valid_amounts, min_size=2, max_size=200))
@settings(suppress_health_check=[HealthCheck.too_slow], max_examples=50)
def test_tier_always_assigned(amounts):
    df = pd.DataFrame({"amount": amounts})
    result = add_amount_tier(df)
    assert result["tier"].isnull().sum() == 0


@given(cats=st.lists(categories, min_size=1, max_size=100))
@settings(suppress_health_check=[HealthCheck.too_slow], max_examples=50)
def test_fill_category_no_nulls(cats):
    df = pd.DataFrame({"category": cats})
    result = fill_category(df)
    assert result["category"].isnull().sum() == 0
'''


def write_test_suite(path: str | Path = "test_pipeline.py") -> Path:
    """Write the pytest + Hypothesis test suite from Extension B."""
    output_path = Path(path)
    output_path.write_text(TEST_PIPELINE_CODE, encoding="utf-8")
    logger.info("{} written", output_path)
    return output_path


# ==================================================
# EXTENSION D AIRFLOW DAG WRITER
# ==================================================

AIRFLOW_DAG_CODE = r'''
"""pipeline_dag.py: Airflow 2 TaskFlow DAG for the validation pipeline."""
from __future__ import annotations

from datetime import datetime, timedelta
import logging

import numpy as np
import pandas as pd
from airflow.decorators import dag, task, task_group
from airflow.models import Variable
from airflow.operators.empty import EmptyOperator
from airflow.utils.trigger_rule import TriggerRule

log = logging.getLogger(__name__)


def sla_miss_callback(dag, task_list, blocking_task_list, slas, blocking_tis):
    log.error("SLA missed for tasks: %s", task_list)


default_args = {
    "owner": "data-engineering",
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "email_on_failure": True,
    "email": ["ops@example.com"],
}


@dag(
    dag_id="validation_pipeline",
    description="ETL pipeline with Pydantic + GE validation",
    schedule="0 6 * * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    sla_miss_callback=sla_miss_callback,
    tags=["etl", "validation", "daily"],
)
def validation_pipeline():
    @task(task_id="ingest", sla=timedelta(minutes=10))
    def ingest_task() -> dict:
        n = int(Variable.get("batch_size", default_var=1000))
        rng = np.random.default_rng()
        df = pd.DataFrame(
            {
                "id": range(n),
                "amount": rng.normal(100, 30, n).round(2),
                "category": rng.choice(
                    ["A", "B", "C", None],
                    n,
                    p=[0.4, 0.3, 0.2, 0.1],
                ),
                "ts": pd.date_range("2024-01-01", periods=n, freq="1h").astype(str),
            }
        )
        path = f"/tmp/raw_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.parquet"
        df.to_parquet(path, index=False)
        log.info("Ingested %s rows -> %s", n, path)
        return {"path": path, "row_count": n}

    @task_group(group_id="validate_group")
    def validate_group(ingest_meta: dict):
        @task(task_id="pydantic_validate")
        def pydantic_validate(meta: dict) -> dict:
            from pydantic import BaseModel, ValidationError, field_validator
            from typing import Literal, Optional

            class TxnRecord(BaseModel):
                id: int
                amount: float
                category: Optional[Literal["A", "B", "C"]]
                ts: str

                @field_validator("amount")
                @classmethod
                def positive(cls, value):
                    if value <= 0:
                        raise ValueError("must be positive")
                    return value

            df = pd.read_parquet(meta["path"])
            valid_rows = []
            errors = []
            for row in df.to_dict("records"):
                try:
                    valid_rows.append(TxnRecord(**row).model_dump())
                except ValidationError:
                    errors.append(row.get("id"))

            valid_df = pd.DataFrame(valid_rows)
            output = meta["path"].replace("raw_", "valid_")
            valid_df.to_parquet(output, index=False)
            pass_rate = len(valid_rows) / len(df)
            log.info("Pydantic: %s/%s valid (%.1f%%)", len(valid_rows), len(df), pass_rate * 100)
            return {"path": output, "pass_rate": pass_rate, "error_count": len(errors)}

        return pydantic_validate(ingest_meta)

    @task.branch(task_id="quality_gate_branch")
    def quality_gate(validate_meta: dict) -> str:
        if validate_meta.get("pass_rate", 0) >= 0.95:
            return "store"
        return "alert_failure"

    @task(task_id="store")
    def store(validate_meta: dict) -> str:
        from pathlib import Path

        df = pd.read_parquet(validate_meta["path"])
        output_dir = Path("data/processed") / f"date={datetime.utcnow().date()}"
        output_dir.mkdir(parents=True, exist_ok=True)
        output = output_dir / "data.parquet"
        df.to_parquet(output, index=False)
        log.info("Stored %s rows -> %s", len(df), output)
        return str(output)

    @task(task_id="alert_failure", trigger_rule=TriggerRule.ALL_DONE)
    def alert_failure(validate_meta: dict):
        log.error("Quality gate failed. pass_rate=%.1f%%", validate_meta.get("pass_rate", 0) * 100)

    done = EmptyOperator(task_id="done", trigger_rule=TriggerRule.ONE_SUCCESS)

    raw_meta = ingest_task()
    valid_meta = validate_group(raw_meta)
    branch = quality_gate(valid_meta)
    ok_path = store(valid_meta)
    fail_path = alert_failure(valid_meta)
    branch >> [ok_path, fail_path] >> done


validation_pipeline()
'''


def write_airflow_dag(path: str | Path = "pipeline_dag.py") -> Path:
    """Write the Airflow DAG from Extension D."""
    output_path = Path(path)
    output_path.write_text(AIRFLOW_DAG_CODE, encoding="utf-8")
    logger.info("{} written", output_path)
    return output_path


# ==================================================
# INLINE PYTEST TESTS
# ==================================================

def test_fill_category_replaces_nulls():
    df = pd.DataFrame({"category": ["A", None, "B"]})
    result = fill_category(df)
    assert result["category"].isnull().sum() == 0


def test_add_amount_tier_assigns_expected_labels():
    df = pd.DataFrame({"amount": [25.0, 75.0, 125.0, 200.0]})
    result = add_amount_tier(df)
    assert list(result["tier"]) == ["low", "medium", "high", "premium"]


def test_normalize_amount_constant_amounts():
    df = pd.DataFrame({"amount": [10.0, 10.0, 10.0]})
    result = normalize_amount(df)
    assert list(result["amount_z"]) == [0.0, 0.0, 0.0]


# ==================================================
# CLI
# ==================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Day 7 validation pipeline.")
    parser.add_argument("--metrics", action="store_true", help="Run with Prometheus metrics.")
    parser.add_argument("--no-ge", action="store_true", help="Skip Great Expectations validation.")
    parser.add_argument("--schedule", action="store_true", help="Start APScheduler instead of one run.")
    parser.add_argument("--write-tests", action="store_true", help="Write test_pipeline.py.")
    parser.add_argument("--write-airflow-dag", action="store_true", help="Write pipeline_dag.py.")
    parser.add_argument("--run-delta", action="store_true", help="Write output to Delta Lake too.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = PipelineConfig()
    use_ge = not args.no_ge

    logger.info("Config loaded: schedule={} | output={}", cfg.schedule_cron, cfg.output_path)

    if args.write_tests:
        write_test_suite()

    if args.write_airflow_dag:
        write_airflow_dag()

    if args.schedule:
        scheduler = start_scheduler(cfg, use_ge=use_ge)
        print("Scheduler is running. Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            stop_scheduler(scheduler)
        return

    if args.metrics:
        start_http_server(8000, registry=registry)
        logger.info("Prometheus metrics available at http://localhost:8000/metrics")
        stats = run_pipeline_instrumented(cfg, use_ge=use_ge)
        print_current_metrics()
    else:
        stats = run_pipeline(cfg, use_ge=use_ge)

    if args.run_delta:
        processed_path = Path(stats["output_path"])
        processed_df = pd.read_parquet(processed_path)
        store_delta(processed_df, mode="overwrite")
        optimize_delta()

    print(f"\nRun stats: {stats}")


if __name__ == "__main__":
    main()
