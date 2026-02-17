# API Reference

## Base URL

```
http://localhost:5000
```

## Authentication

No authentication is enforced by default. For production deployments, implement API key or OAuth2 authentication in front of the service.

---

## Endpoints

### Health Check

**GET /health**

Returns system health and model status.

```json
{
  "status": "healthy",
  "timestamp": "2026-02-17T12:00:00",
  "model_trained": true
}
```

---

### Collect Metrics

**POST /api/v1/collect**

Collect build metrics from a CI/CD source.

Request:
```json
{
  "source": "jenkins",
  "count": 100
}
```

Sources: `jenkins`, `github`, `gitlab`

Response:
```json
{
  "success": true,
  "metrics_collected": 150,
  "source": "jenkins",
  "filepath": "./data/metrics/jenkins_20260217_120000.json"
}
```

---

### Train Model

**POST /api/v1/train**

Train the ensemble anomaly detection model on stored historical data.

Request:
```json
{
  "days": 30,
  "contamination": 0.1,
  "use_ensemble": true
}
```

Response:
```json
{
  "success": true,
  "training_stats": {
    "ensemble_size": 2,
    "successful": 2,
    "failed": 0
  }
}
```

---

### Detect Anomalies (Single Model)

**POST /api/v1/detect**

Detect anomalies using the base Isolation Forest + statistical method. Preserved for backward compatibility.

Request:
```json
{
  "threshold": 3.0,
  "send_alerts": true
}
```

---

### Detect Anomalies (Ensemble)

**POST /api/v1/ensemble-detect**

Detect anomalies using the full ensemble. Multiple models must agree before an anomaly is reported, significantly reducing false positives.

Request:
```json
{
  "send_alerts": true
}
```

Response:
```json
{
  "success": true,
  "total_samples": 100,
  "anomalies_detected": 4,
  "voting_stats": {
    "total_individual_detections": 12,
    "ensemble_detections": 4,
    "reduction_rate": 0.67
  },
  "anomalies": [
    {
      "confidence": 0.85,
      "severity": "high",
      "detectors_agreed": ["isolation_forest", "lstm"],
      "avg_score": 0.73,
      "data": { "job_name": "build-api", "duration": 800 }
    }
  ]
}
```

---

### Predict Next Build

**POST /api/v1/predict**

Predict metrics for the next build using the LSTM time-series predictor.

Request:
```json
{
  "job_name": "build-api",
  "sequence_length": 20
}
```

Response:
```json
{
  "success": true,
  "job_name": "build-api",
  "predictions": {
    "duration": {
      "predicted": 312.5,
      "lower_bound": 250.0,
      "upper_bound": 375.0,
      "confidence": 0.82
    }
  }
}
```

---

### Root Cause Analysis

**POST /api/v1/analyze-cause**

Analyse a specific anomaly to identify probable root causes and recommendations.

Request:
```json
{
  "anomaly": {
    "data": { "job_name": "build-api", "duration": 800, "timestamp": "..." },
    "anomaly_features": [
      { "feature": "duration", "value": 800, "expected": 300, "z_score": 4.5 }
    ]
  },
  "context": {
    "commit_changes": { "files_changed": 45 },
    "concurrent_builds": 7
  }
}
```

Response:
```json
{
  "success": true,
  "analysis": {
    "probable_causes": [
      {
        "cause": "Increased test count",
        "description": "Test suite grew by 50%",
        "confidence": 0.95
      }
    ],
    "similar_incidents": [...],
    "recommendations": [
      {
        "action": "Optimize test suite",
        "priority": "high",
        "details": "Parallelise tests or remove redundant ones",
        "impact": "Can reduce build time by 20-40%"
      }
    ]
  }
}
```

---

### Get Insights

**GET /api/v1/insights**

Return a summary of insights from the root cause analyzer across all analyzed incidents.

---

### Get Recent Anomalies

**GET /api/v1/anomalies?hours=24**

Retrieve anomalies detected in the last N hours.

---

### Get Report

**GET /api/v1/report**

Generate a summary report of metrics and anomalies.

---

### Get Status

**GET /api/v1/status**

Return current system status including model training state and data counts.

---

### Run Full Pipeline

**POST /api/v1/pipeline**

Execute collection, training, and detection in sequence.

---

## Flaky Test Endpoints

### Analyze Flaky Tests

**POST /api/v1/flaky-tests/analyze**

Analyse test execution history to detect intermittently failing tests.

Request:
```json
{ "days": 30 }
```

Response:
```json
{
  "success": true,
  "flaky_tests_detected": 3,
  "summary": {
    "total_flaky_tests": 3,
    "by_severity": { "high": 1, "medium": 2 },
    "estimated_wasted_time_hours": 8.5
  },
  "flaky_tests": [
    {
      "test_name": "test_payment_processing",
      "flakiness_score": 87.5,
      "severity": "high",
      "failure_rate": 0.35,
      "total_runs": 50,
      "failures": 18,
      "flip_flops": 12
    }
  ]
}
```

### Get Flaky Tests

**GET /api/v1/flaky-tests**

Return the current flaky test summary.

### Get Flaky Test Detail

**GET /api/v1/flaky-tests/{test_name}**

Return full detail for a specific flaky test including execution history and recommendations.

```json
{
  "success": true,
  "test": {
    "test_name": "test_payment_processing",
    "flakiness_score": 87.5,
    "severity": "high",
    "failure_rate": 0.35,
    "consecutive_failures": 2,
    "flip_flops": 12,
    "recommendations": [
      {
        "issue": "High variability in results",
        "likely_cause": "Race condition or timing dependency",
        "action": "Add explicit waits or synchronization",
        "priority": "high",
        "effort": "medium"
      }
    ]
  }
}
```

---

## Smart Alert Endpoints

### Get Alert Rules

**GET /api/v1/alerts/rules**

List all configured routing rules.

### Add Alert Rule

**POST /api/v1/alerts/rules**

Add a routing rule. Rules are evaluated in insertion order; first match wins.

```json
{
  "name": "frontend-team",
  "job_pattern": "frontend",
  "min_severity": "medium",
  "channels": ["slack"],
  "team_name": "Frontend",
  "slack_webhook": "https://hooks.slack.com/services/..."
}
```

Fields:
- `name` (required): Unique rule identifier
- `job_pattern`: Substring to match against job name. Omit to match all jobs.
- `min_severity`: Minimum severity to route. One of `low`, `medium`, `high`, `critical`.
- `channels`: Array of `slack`, `email`, `webhook`.
- `slack_webhook`: Team-specific webhook override.

### Remove Alert Rule

**DELETE /api/v1/alerts/rules/{name}**

### Get Maintenance Windows

**GET /api/v1/alerts/maintenance**

List currently active maintenance windows.

### Add Maintenance Window

**POST /api/v1/alerts/maintenance**

Suppress alerts during a planned maintenance period.

```json
{
  "name": "planned-deploy",
  "start": "2026-02-18T02:00:00",
  "end":   "2026-02-18T04:00:00",
  "affected_jobs": ["deploy-prod", "deploy-staging"]
}
```

Omit `affected_jobs` to suppress alerts for all jobs during the window.

### Remove Maintenance Window

**DELETE /api/v1/alerts/maintenance/{name}**

### Get Alert Statistics

**GET /api/v1/alerts/stats**

Return suppression and delivery statistics.

```json
{
  "success": true,
  "stats": {
    "total_received": 120,
    "total_sent": 18,
    "suppressed_duplicate": 45,
    "suppressed_maintenance": 12,
    "suppressed_rate_limit": 5,
    "suppressed_severity": 40,
    "suppression_rate": 0.85,
    "pending_in_batch": 0,
    "active_maintenance_windows": 1,
    "registered_rules": 3,
    "alerts_last_hour": 4
  }
}
```

### Flush Alert Batch

**POST /api/v1/alerts/flush**

Immediately send all pending batched alerts without waiting for the batch window to expire.

---

## Prometheus Metrics

Exposed on port 8000 at `/metrics`.

| Metric | Type | Description |
|--------|------|-------------|
| `cicd_build_duration_seconds` | Histogram | Build duration |
| `cicd_build_total` | Counter | Builds by result |
| `cicd_queue_time_seconds` | Histogram | Queue time |
| `cicd_test_count` | Gauge | Tests per build |
| `cicd_failure_count` | Gauge | Failures per build |
| `cicd_anomaly_score` | Gauge | Anomaly score |
| `cicd_anomaly_total` | Counter | Total anomalies |
| `cicd_model_accuracy` | Gauge | Model accuracy |
| `cicd_model_last_trained_timestamp` | Gauge | Last training time |
| `cicd_active_jobs` | Gauge | Active job count |
| `cicd_data_points_total` | Counter | Total data points |

---

## Error Responses

**400 Bad Request**
```json
{ "error": "Missing required field: name" }
```

**404 Not Found**
```json
{ "error": "Test test_login not found or not flaky" }
```

**500 Internal Server Error**
```json
{ "error": "Failed to connect to Jenkins server" }
```
