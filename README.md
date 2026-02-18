# CI/CD Anomaly Detection System

AI-powered anomaly detection system for CI/CD pipelines. Automatically learns normal pipeline behaviour, identifies issues before they impact production, and routes intelligent alerts to the right teams.

---

## Features

- **Multi-Source Data Collection**: Jenkins, GitHub Actions, and GitLab CI
- **Ensemble ML Detection**: Isolation Forest, LSTM time-series predictor, and statistical z-score methods vote together, reducing false positives by up to 60%
- **Root Cause Analysis**: Explains why an anomaly occurred and provides ranked, actionable recommendations
- **Flaky Test Detection**: Tracks test execution history to identify intermittently failing tests with severity scoring and fix suggestions
- **Smart Alerting**: Batching, deduplication, team-specific routing, maintenance windows, and rate limiting built on top of Slack, email, and webhook delivery
- **Real-Time Monitoring**: Prometheus metrics exporter with a pre-built Grafana dashboard
- **REST API**: Full API covering collection, training, detection, analysis, and alert management
- **Automated Scheduling**: Periodic collection every 15 minutes, daily model retraining, weekly data cleanup

---

## Architecture

```
Data Sources
  Jenkins  --+
  GitHub   --+--> Collectors --> Data Storage --> ML Engine
  GitLab   --+                                      |
                                                     |
                              +----------------------+
                              |                      |
                         Ensemble                Root Cause
                         Detector                Analyzer
                         (IF+LSTM+Stats)              |
                              |                      |
                              +----------+-----------+
                                         |
                              Smart Alert Manager
                              (batch/dedup/routing)
                                         |
                         +--------------+-----------+
                       Slack           Email      Webhook

                    Prometheus Exporter --> Grafana Dashboard
```

---

## Prerequisites

- Python 3.8 or higher
- Docker and Docker Compose (for containerised deployment)
- Access to Jenkins, GitHub, or GitLab (at least one)
- Prometheus and Grafana (included in docker-compose.yml)

---

## Quick Start

### 1. Setup

```bash
cd cicd-anomaly-detection
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.template .env
nano .env
```

Minimum required configuration:

```env
JENKINS_URL=http://your-jenkins:8080
JENKINS_USER=admin
JENKINS_TOKEN=your_api_token
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

### 3. Start with Docker Compose

```bash
docker-compose up -d
# API:        http://localhost:5000
# Prometheus: http://localhost:9090
# Grafana:    http://localhost:3000  (admin / admin)
```

### 4. Start Manually

```bash
python api/app.py     # Terminal 1
python scheduler.py   # Terminal 2
```

---

## Core Workflow

```bash
# Collect historical builds
curl -X POST http://localhost:5000/api/v1/collect \
  -H "Content-Type: application/json" \
  -d '{"source": "jenkins", "count": 200}'

# Train the ensemble
curl -X POST http://localhost:5000/api/v1/train \
  -H "Content-Type: application/json" \
  -d '{"days": 30}'

# Detect anomalies
curl -X POST http://localhost:5000/api/v1/ensemble-detect \
  -H "Content-Type: application/json" \
  -d '{"send_alerts": true}'

# Analyze root cause
curl -X POST http://localhost:5000/api/v1/analyze-cause \
  -H "Content-Type: application/json" \
  -d '{"anomaly": {...}}'

# Check flaky tests
curl -X POST http://localhost:5000/api/v1/flaky-tests/analyze \
  -H "Content-Type: application/json" \
  -d '{"days": 30}'
```

---

## Smart Alerting

### Key Behaviours

**Deduplication**: Identical alerts for the same job and features are suppressed within a configurable window (default 5 minutes).

**Batching**: Alerts are collected for 60 seconds then sent as one grouped message, preventing floods during cascading failures.

**Team Routing**: Rules match job name patterns and direct alerts to different Slack webhooks or channels.

**Maintenance Windows**: Registered via API; alerts for affected jobs are silently suppressed during the window.

**Rate Limiting**: Hard cap of 20 alerts per hour prevents runaway notifications.

### Environment Variables

```env
ALERT_BATCH_WINDOW=60
ALERT_DEDUP_WINDOW=300
ALERT_MAX_PER_HOUR=20
```

### Routing Rules via API

```bash
curl -X POST http://localhost:5000/api/v1/alerts/rules \
  -H "Content-Type: application/json" \
  -d '{
    "name": "frontend-team",
    "job_pattern": "frontend",
    "min_severity": "medium",
    "channels": ["slack"],
    "slack_webhook": "https://hooks.slack.com/services/FRONTEND/WEBHOOK"
  }'
```

### Maintenance Windows via API

```bash
curl -X POST http://localhost:5000/api/v1/alerts/maintenance \
  -H "Content-Type: application/json" \
  -d '{
    "name": "planned-deploy",
    "start": "2026-02-18T02:00:00",
    "end":   "2026-02-18T04:00:00",
    "affected_jobs": ["deploy-prod", "deploy-staging"]
  }'
```

---

## Project Structure

```
cicd-anomaly-detection/
├── api/
│   ├── app.py                  # REST API server
│   ├── alerting.py             # Base alert manager
│   └── smart_alerting.py       # Smart alert layer
├── collectors/
│   ├── jenkins_collector.py
│   ├── github_collector.py
│   ├── gitlab_collector.py
│   └── prometheus_exporter.py
├── ml/
│   ├── anomaly_detector.py
│   ├── ensemble_detector.py
│   ├── lstm_predictor.py
│   ├── root_cause_analyzer.py
│   ├── flaky_test_detector.py
│   └── data_storage.py
├── config/
│   ├── config.yaml
│   ├── prometheus.yml
│   └── alert_rules.yml
├── dashboards/
│   └── grafana-dashboard.json
├── tests/
│   ├── test_anomaly_detector.py
│   └── test_integration.py
├── scheduler.py
├── demo.py
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── .env.template
```

---

## Scheduling

| Task | Schedule |
|------|----------|
| Metrics collection | Every 15 minutes |
| Model retraining | Daily at 02:00 |
| Data cleanup | Weekly, Sunday at 03:00 |

---

## Troubleshooting

**Model not training**: Check `curl http://localhost:5000/api/v1/status` - need at least 100 samples.

**No anomalies detected**: Lower `ANOMALY_THRESHOLD` in config, retrain with recent data.

**Alerts not sending**: Check `curl http://localhost:5000/api/v1/alerts/stats` for suppression reasons.

**Connection error**: Verify credentials with `curl -u user:token http://jenkins:8080/api/json`.

---

## Security

- Store credentials in `.env` only; never commit it to version control
- Use read-only API tokens where possible
- Use HTTPS for all webhook URLs in production
- Rotate tokens regularly

---

## Best Practices

1. Collect at least 200 builds before initial training
2. Retrain weekly or after major pipeline changes
3. Tune `ANOMALY_THRESHOLD` based on observed false positive rate
4. Configure routing rules to direct alerts to the correct team
5. Register maintenance windows before planned deployments
6. Review flaky test reports weekly; prioritise critical-severity tests
