# Quick Start Guide - CI/CD Anomaly Detection System

## 5-Minute Setup

### Prerequisites
- Python 3.8+
- Docker and Docker Compose (optional, recommended)
- Jenkins or GitHub repository (for production use)

### Installation

```bash
# 1. Navigate to project directory
cd cicd-anomaly-detection

# 2. Run setup script
./setup.sh

# 3. Configure credentials
nano .env  # Add your Jenkins/GitHub credentials

# 4. Run demo to verify
python demo.py
```

## Three Deployment Options

### Option 1: Docker Compose (Recommended)

```bash
# Start everything (API, Scheduler, Prometheus, Grafana)
docker-compose up -d

# Access services:
# - API: http://localhost:5000
# - Grafana: http://localhost:3000 (admin/admin)
# - Prometheus: http://localhost:9090

# View logs
docker-compose logs -f

# Stop everything
docker-compose down
```

### Option 2: Python Scripts

```bash
# Terminal 1: Start API
python api/app.py

# Terminal 2: Start scheduler
python scheduler.py

# Terminal 3: Test API
curl http://localhost:5000/health
```

### Option 3: Manual Testing

```bash
# Run demo with mock data
python demo.py

# Collect real data
curl -X POST http://localhost:5000/api/v1/collect \
  -H "Content-Type: application/json" \
  -d '{"source": "jenkins", "count": 100}'

# Train model
curl -X POST http://localhost:5000/api/v1/train

# Detect anomalies
curl -X POST http://localhost:5000/api/v1/detect
```

##  First-Time Workflow

```bash
# 1. Collect historical data (need 100+ builds)
curl -X POST http://localhost:5000/api/v1/collect \
  -d '{"source": "jenkins", "count": 200}'

# 2. Train the model
curl -X POST http://localhost:5000/api/v1/train \
  -d '{"days": 30, "contamination": 0.1}'

# 3. Start monitoring
curl -X POST http://localhost:5000/api/v1/pipeline

# 4. Check status
curl http://localhost:5000/api/v1/status

# 5. View recent anomalies
curl http://localhost:5000/api/v1/anomalies?hours=24
```

##  Setting Up Alerts

### Slack Integration

1. Create webhook: https://api.slack.com/apps → Incoming Webhooks
2. Add to `.env`:
   ```
   SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK
   ```
3. Test:
   ```bash
   curl -X POST http://localhost:5000/api/v1/detect \
     -d '{"send_alerts": true}'
   ```

### Email Alerts

Add to `.env`:
```
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
ALERT_EMAIL=team@company.com
```

##  Using Grafana

1. Access: http://localhost:3000
2. Login: admin/admin
3. Import dashboard:
   - Go to Dashboards → Import
   - Upload: `dashboards/grafana-dashboard.json`
4. View real-time metrics

## 🎮 API Examples

### Collect from Jenkins
```bash
curl -X POST http://localhost:5000/api/v1/collect \
  -H "Content-Type: application/json" \
  -d '{
    "source": "jenkins",
    "count": 100
  }'
```

### Collect from GitHub
```bash
curl -X POST http://localhost:5000/api/v1/collect \
  -H "Content-Type: application/json" \
  -d '{
    "source": "github",
    "count": 100
  }'
```

### Train with Custom Settings
```bash
curl -X POST http://localhost:5000/api/v1/train \
  -H "Content-Type: application/json" \
  -d '{
    "days": 30,
    "contamination": 0.15
  }'
```

### Detect with Custom Threshold
```bash
curl -X POST http://localhost:5000/api/v1/detect \
  -H "Content-Type: application/json" \
  -d '{
    "threshold": 2.5,
    "send_alerts": true
  }'
```

### Get Summary Report
```bash
curl http://localhost:5000/api/v1/report | jq .
```

## 🧪 Testing Individual Components

```bash
# Test Jenkins collector
python collectors/jenkins_collector.py

# Test GitHub collector
python collectors/github_collector.py

# Test ML model
python ml/anomaly_detector.py

# Test data storage
python ml/data_storage.py

# Run unit tests
pytest tests/ -v
```

##  Common Issues

### "Model not trained"
```bash
# Solution: Train the model first
curl -X POST http://localhost:5000/api/v1/train
```

### "Not enough data"
```bash
# Solution: Collect more metrics
curl -X POST http://localhost:5000/api/v1/collect \
  -d '{"count": 200}'
```

### "Connection refused"
```bash
# Solution: Check credentials in .env
# Test Jenkins connection:
curl -u username:token http://jenkins-url/api/json
```

### No anomalies detected
```bash
# Solution: Lower the threshold
curl -X POST http://localhost:5000/api/v1/detect \
  -d '{"threshold": 2.0}'
```

##  Understanding Results

### Anomaly Response Example
```json
{
  "index": 5,
  "max_z_score": 4.5,
  "anomaly_features": [
    {
      "feature": "duration",
      "value": 800.0,
      "expected": 300.0,
      "z_score": 4.5
    }
  ],
  "data": {
    "job_name": "build-api",
    "duration": 800.0,
    "result": "FAILURE"
  }
}
```

**What this means:**
- Build took 800s instead of expected 300s
- Z-score of 4.5 = very unusual (>99.99% probability of anomaly)
- Build failed, worth investigating

##  Configuration Tips

### Adjust Sensitivity

**Too many false positives?**
- Increase threshold: `"threshold": 3.5`
- Increase contamination: `"contamination": 0.15`

**Missing real issues?**
- Decrease threshold: `"threshold": 2.0`
- Decrease contamination: `"contamination": 0.05`

### Optimize Performance

**Large datasets:**
- Limit collection: `"count": 100`
- Use sampling for training
- Schedule training for off-hours

**Frequent alerts:**
- Batch alerts in scheduler
- Set minimum severity threshold
- Use digest mode (hourly summary)

##  Production Checklist

- [ ] Configure real Jenkins/GitHub credentials
- [ ] Set up Slack webhook for alerts
- [ ] Configure email SMTP settings
- [ ] Enable HTTPS for API
- [ ] Set up monitoring (Grafana)
- [ ] Configure log rotation
- [ ] Set up backup for models and data
- [ ] Test alert delivery
- [ ] Document team response procedures
- [ ] Schedule regular model retraining

##  File Structure

```
cicd-anomaly-detection/
├── api/
│   ├── app.py              # REST API
│   └── alerting.py         # Alerts
├── collectors/
│   ├── jenkins_collector.py
│   ├── github_collector.py
│   └── prometheus_exporter.py
├── ml/
│   ├── anomaly_detector.py # ML models
│   └── data_storage.py     # Data management
├── config/                 # Configuration files
├── dashboards/            # Grafana dashboards
├── tests/                 # Unit tests
├── demo.py               # Quick demo
├── scheduler.py          # Automation
├── docker-compose.yml    # Docker setup
└── README.md            # Full docs
```

##  Getting Help

1. Check logs: `docker-compose logs -f`
2. Test health: `curl http://localhost:5000/health`
3. Review README.md for detailed docs
4. Check API.md for endpoint reference
5. Run demo.py to verify setup

##  Next Steps

1. **Configure production credentials** in `.env`
2. **Start Docker stack**: `docker-compose up -d`
3. **Collect initial data**: Run for 24-48 hours
4. **Train model**: POST to `/api/v1/train`
5. **Monitor Grafana**: Check http://localhost:3000
6. **Tune thresholds**: Based on false positive rate
7. **Document incidents**: Track detected anomalies

---

## Additional Resources

- Full Documentation: README.md
- API Reference: API.md
- Architecture: OVERVIEW.md
- Run Tests: `pytest tests/`

---

**CI/CD Anomaly Detection System - Production Ready**
