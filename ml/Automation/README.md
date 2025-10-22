# ML Automation

Purpose
- Automation utilities and orchestrations for AMTTP ML workflows.
- Scheduled retraining, data ingestion cron jobs, model promotion automation, and experiment rollout automation.

Contents
- CI/CD automation scripts for training and model packaging
- Kubernetes cronjob manifests for scheduled retrain and batch scoring
- Airflow / Prefect DAG examples for data ingestion and ETL
- Runner scripts to trigger Memgraph enrichment via proxy and produce Merkle batches

Guidelines
- Keep production secrets out of repo; use KMS and environment variables.
- Use dataset manifests and model metadata for reproducibility.
- Place long-running or infra-specific manifests under ml/Automation/infra/.