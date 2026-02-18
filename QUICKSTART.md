# Quick Start Guide

## Prerequisites

- Python 3.8 or higher
- Docker and Docker Compose (optional but recommended)
- Access to Jenkins, GitHub Actions, or GitLab CI

---

## Installation

```bash
cd cicd-anomaly-detection
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.template .env
```

---

## Deployment Options

### Option 1: Docker Compose (Recommended)

```bash
docker-compose up -d

# Services:
# API:        http://localhost:5000
# Grafana:    http://localhost:3000  (admin / admin)
# Prometheus: http://localhost:9090

docker-compose logs -f      # stream logs
docker-compose down         # stop all services
```

### Option 2: Manual Python

```bash
python api/app.py     # Terminal 1: API server
python scheduler.py   # Terminal 2: Collection and detection scheduler
```

### Option 3: Quick Demo

```bash
python demo.py
```

---

## First-Time Workflow

### Step 1: Configure Credentials

Edit `.env` with your credentials:

```env
# Jenkins (at least one source required)
JENKINS_URL=http://your-jenkins:8080
JENKINS_USER=admin
JENKINS_TOKEN=your_api_token

# GitHub Actions (optional)
GITHUB_TOKEN=your_github_token
GITHUB_REPO=owner/repository

# GitLab CI (optional)
GITLAB_URL=https://gitlab.com
GITLAB_TOKEN=your_gitlab_token
GITLAB_PROJECT=group/project

# Slack alerts (optional)
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL

# Email alerts (optional)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your_app_password
ALERT_EMAIL=alerts@yourcompany.com

# Smart alerting (optional - defaults shown)
ALERT_BATCH_WINDOW=60
ALERT_DEDUP_WINDOW=300
ALERT_MAX_PER_HOUR=20
```

### Step 2: Collect Historical Data

Collect at least 100 builds before training. 200 or more is recommended for a reliable model.

```bash
# Jenkins
curl -X POST http://localhost:5000/api/v1/collect \
  -H "Content-Type: application/json" \
  -d '{"source": "jenkins", "count": 200}'

# GitHub Actions
curl -X POST http://localhost:5000/api/v1/collect \
  -H "Content-Type: application/json" \
  -d '{"source": "github", "count": 200}'

# GitLab CI
curl -X POST http://localhost:5000/api/v1/collect \
  -H "Content-Type: application/json" \
  -d '{"source": "gitlab", "count": 200}'
```

### Step 3: Train the Ensemble

```bash
curl -X POST http://localhost:5000/api/v1/train \
  -H "Content-Type: application/json" \
  -d '{"days": 30}'
```

### Step 4: Detect Anomalies

```bash
curl -X POST http://localhost:5000/api/v1/ensemble-detect \
  -H "Content-Type: application/json" \
  -d '{"send_alerts": true}'
```

### Step 5: Check Status

```bash
curl http://localhost:5000/api/v1/status
```

---

## Smart Alerting Setup

### Add Team Routing Rules

Configure which jobs alert which teams.

```bash
# Frontend team - medium severity and above only
curl -X POST http://localhost:5000/api/v1/alerts/rules \
  -H "Content-Type: application/json" \
  -d '{
    "name": "frontend-team",
    "job_pattern": "frontend",
    "min_severity": "medium",
    "channels": ["slack"],
    "slack_webhook": "https://hooks.slack.com/services/FRONTEND/CHANNEL"
  }'

# Production on-call - high severity and above, Slack and email
curl -X POST http://localhost:5000/api/v1/alerts/rules \
  -H "Content-Type: application/json" \
  -d '{
    "name": "production-oncall",
    "job_pattern": "deploy-prod",
    "min_severity": "high",
    "channels": ["slack", "email"],
    "team_name": "On-Call"
  }'

# Default catch-all rule
curl -X POST http://localhost:5000/api/v1/alerts/rules \
  -H "Content-Type: application/json" \
  -d '{
    "name": "default",
    "min_severity": "medium",
    "channels": ["slack"]
  }'
```

### Register a Maintenance Window

```bash
curl -X POST http://localhost:5000/api/v1/alerts/maintenance \
  -H "Content-Type: application/json" \
  -d '{
    "name": "weekly-deploy",
    "start": "2026-02-18T02:00:00",
    "end":   "2026-02-18T04:00:00",
    "affected_jobs": ["deploy-prod", "deploy-staging"]
  }'
```

### View Alert Statistics

```bash
curl http://localhost:5000/api/v1/alerts/stats
```

---

## Flaky Test Detection

```bash
# Analyze last 30 days
curl -X POST http://localhost:5000/api/v1/flaky-tests/analyze \
  -H "Content-Type: application/json" \
  -d '{"days": 30}'

# View summary
curl http://localhost:5000/api/v1/flaky-tests

# Get recommendations for a specific test
curl http://localhost:5000/api/v1/flaky-tests/test_user_login
```

---

## Grafana Dashboard

1. Open http://localhost:3000 and log in with admin / admin
2. Go to Dashboards then Browse
3. Import `dashboards/grafana-dashboard.json`

Dashboard panels include build rate by job, anomaly detection rate, duration percentiles, result distribution, anomaly scores, and model status.

---

## Verify Everything is Working

```bash
# Health check
curl http://localhost:5000/health

# System status
curl http://localhost:5000/api/v1/status

# Alert stats (check suppression is working)
curl http://localhost:5000/api/v1/alerts/stats

# Run integration tests
python tests/test_integration.py
```

Expected output from integration tests: 6/6 tests passed.

---

## Ongoing Operations

### Daily

- Review the Grafana dashboard for anomaly trends
- Check alert statistics to confirm rules are routing correctly

### Weekly

- Retrain the model with the latest data:
  ```bash
  curl -X POST http://localhost:5000/api/v1/train -d '{"days": 30}'
  ```
- Run flaky test analysis and assign critical-severity tests for fixing

### After Major Pipeline Changes

- Retrain the model immediately so the new behaviour is learned quickly
- Adjust `ANOMALY_THRESHOLD` if false positive rate increases

---

## Common Commands Reference

```bash
# Collect from all sources
curl -X POST http://localhost:5000/api/v1/collect -d '{"source": "jenkins", "count": 100}'
curl -X POST http://localhost:5000/api/v1/collect -d '{"source": "github",  "count": 100}'
curl -X POST http://localhost:5000/api/v1/collect -d '{"source": "gitlab",  "count": 100}'

# Train
curl -X POST http://localhost:5000/api/v1/train -d '{"days": 30}'

# Detect
curl -X POST http://localhost:5000/api/v1/ensemble-detect -d '{"send_alerts": true}'

# Recent anomalies
curl "http://localhost:5000/api/v1/anomalies?hours=24"

# Report
curl http://localhost:5000/api/v1/report

# Flaky tests
curl -X POST http://localhost:5000/api/v1/flaky-tests/analyze -d '{"days": 30}'

# Alert rules
curl http://localhost:5000/api/v1/alerts/rules
curl http://localhost:5000/api/v1/alerts/stats

# Flush pending batch
curl -X POST http://localhost:5000/api/v1/alerts/flush
```
