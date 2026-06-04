# MSF ETL vs ELT Decision

## Problem Statement

Médecins Sans Frontières (MSF) runs humanitarian medical operations in 70+ countries. They want to build a unified data platform that collects field clinic data from around 400 field sites into a central analytics hub for the Geneva headquarters team.

## Final Choice: ETL

| Constraint | What it means | ETL or ELT? |
|---|---|---|
| **Infrastructure** | HQ already uses **BigQuery**, field sites upload **daily batch CSVs**, no real-time streaming | ETL works well because batch processing is enough |
| **Patient data sensitivity** | Data has names, ages, diagnoses, GPS locations. It must be **fully anonymized before entering central platform** | Strong reason for **ETL** |
| **Analytics requirements** | Analysts need ad-hoc queries and flexible reports | After ETL, use BigQuery/dbt-style ELT for analytics |
| **Data format** | 400 sites have different column names, date formats, and local labels | ETL is needed for normalization before loading |
| **Latency tolerance** | 24-hour delay is acceptable, forecasting is weekly | ETL batch pipeline is fine |

## Answer

I would use **ETL**, because sensitive patient data must be anonymized and normalized before it reaches the central BigQuery platform.

Since the field sites upload daily CSV batches and 24-hour latency is acceptable, batch ETL is suitable. After clean and anonymized data is loaded into BigQuery, we can use ELT/dbt-style transformations for flexible analytics and ad-hoc reporting.
