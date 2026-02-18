# CI/CD Anomaly Detection System - Project Overview

## Description

A production-ready AI-powered anomaly detection system for CI/CD pipelines. The system automatically learns what normal pipeline behaviour looks like, flags deviations as they occur, identifies the likely cause, and delivers actionable alerts to the right team — all without manual threshold configuration.

---

## Key Features

### 1. Multi-Source Data Collection

Collects build metrics from Jenkins, GitHub Actions, and GitLab CI through their respective REST APIs. Metrics include build duration, queue time, test count, failure count, step count, and result status. Collection runs automatically every 15 minutes via the built-in scheduler.

### 2. Ensemble ML Detection

Three detection methods run in parallel and must agree before flagging an anomaly:

- **Isolation Forest**: Unsupervised ML model trained on historical build data. Learns the normal distribution of all features and isolates outliers.
- **LSTM Predictor**: Sequence-based model that learns time-series patterns per job. Detects anomalies that appear normal in isolation but are unusual given recent history.
- **Statistical Z-Score**: Per-feature z-score calculation. Identifies which specific metric is anomalous and by how much.

The ensemble vote reduces false positives by 40-60% compared to any single method alone.

### 3. Root Cause Analysis

For every anomaly above a confidence threshold, the system runs a root cause analysis that:

- Ranks probable causes by confidence (infrastructure issues, code changes, test suite changes, resource contention)
- Links to similar past incidents and their resolutions
- Provides prioritised recommendations with estimated impact

### 4. Flaky Test Detection

Tracks every test execution across all builds. A test is considered flaky when it has both passes and failures within the lookback period and a failure rate at or above the configured threshold (default 10%). Each flaky test receives:

- A flakiness score from 0 to 100
- A severity rating: low, medium, high, or critical
- Pattern analysis: failure rate, flip-flops (status transitions), consecutive failures
- Recommendations specific to the detected pattern (race conditions, external dependencies, test design issues)
- Estimated developer time wasted per month

### 5. Smart Alerting

A dedicated smart alert layer wraps the base Slack, email, and webhook delivery without modifying it. The layer provides:

- **Deduplication**: Identical alerts for the same job and anomalous features are suppressed within a configurable window (default 5 minutes)
- **Batching**: Alerts are collected for a configurable window (default 60 seconds) and sent as one grouped message
- **Team Routing**: Rules match job name patterns and direct alerts to team-specific Slack webhooks or channels with configurable severity thresholds
- **Maintenance Windows**: Registered via API; all alerts for affected jobs are suppressed during the window
- **Rate Limiting**: Configurable hard cap on alerts per hour prevents notification floods
- **State Persistence**: Deduplication fingerprints and rate limit counters survive process restarts

### 6. Real-Time Monitoring

Prometheus metrics are exported on port 8000. A pre-built Grafana dashboard covers build rate, anomaly rate, duration percentiles, result distribution, and model status.

### 7. REST API

Full REST API for every system function. See API.md for complete reference.

---

## Technical Design Decisions

### Why Ensemble Detection

Single models produce too many false positives in CI/CD environments because pipeline durations and failure rates vary legitimately across teams, branches, and time of day. Requiring multiple independent models to agree before raising an alert dramatically reduces noise while maintaining sensitivity to genuine incidents.

### Why a Wrapper for Smart Alerting

Rather than modifying the existing AlertManager, the SmartAlertManager wraps it. This means all existing call sites continue to work identically. The smart layer is purely additive — it can be removed without any other code changes.

### Why State Persistence for Alerts

Deduplication state is written to disk after every decision. If the process restarts during a noisy incident, the system does not send a second flood of alerts for the same failures that were already notified.

---

## Data Flow

```
1. Scheduler (every 15 min)
   --> Collectors pull latest builds from Jenkins / GitHub / GitLab
   --> Metrics stored as JSON in ./data/metrics/

2. Ensemble Detection
   --> Load last N days of metrics from storage
   --> All three models score each build
   --> Voting: build is anomalous if enough models agree
   --> High-confidence anomalies passed to Root Cause Analyzer
   --> Results stored in ./data/anomalies/

3. Smart Alert Manager
   --> Receives anomaly for each detected build
   --> Applies maintenance window, dedup, rate limit, and severity checks
   --> Collects passing alerts in batch buffer
   --> After batch window: sends one message to routed channel(s)
   --> Records fingerprint and timestamp to disk

4. Scheduler (daily at 02:00)
   --> Retrains ensemble on last 30 days of data
   --> Saves updated models to ./models/
```

---

## Component Summary

| Component | File | Responsibility |
|-----------|------|----------------|
| REST API | api/app.py | HTTP endpoint handler |
| Base Alert Manager | api/alerting.py | Slack, email, webhook delivery |
| Smart Alert Manager | api/smart_alerting.py | Batching, dedup, routing, maintenance, rate limiting |
| Anomaly Detector | ml/anomaly_detector.py | Isolation Forest + z-score |
| Ensemble Detector | ml/ensemble_detector.py | Multi-model voting |
| LSTM Predictor | ml/lstm_predictor.py | Time-series prediction |
| Root Cause Analyzer | ml/root_cause_analyzer.py | Cause ranking and recommendations |
| Flaky Test Detector | ml/flaky_test_detector.py | Test reliability tracking |
| Data Storage | ml/data_storage.py | JSON persistence layer |
| Jenkins Collector | collectors/jenkins_collector.py | Jenkins REST API client |
| GitHub Collector | collectors/github_collector.py | GitHub Actions API client |
| GitLab Collector | collectors/gitlab_collector.py | GitLab CI API client |
| Prometheus Exporter | collectors/prometheus_exporter.py | Metrics exposition |
| Scheduler | scheduler.py | Periodic task orchestration |

---

## Performance Characteristics

| Metric | Value |
|--------|-------|
| Collection cycle | 15 minutes |
| Detection latency | Under 5 seconds for 1,000 builds |
| False positive reduction | 40-60% vs single model |
| Minimum training samples | 100 builds |
| Recommended training samples | 200+ builds |
| Alert dedup window | 5 minutes (configurable) |
| Alert batch window | 60 seconds (configurable) |
| Alert rate limit | 20 per hour (configurable) |
| Supported platforms | Jenkins, GitHub Actions, GitLab CI |

---

## Deployment

The system is packaged as Docker containers orchestrated with Docker Compose. The stack includes the anomaly detection API, scheduler, Prometheus, and Grafana.

See QUICKSTART.md for step-by-step deployment instructions.
