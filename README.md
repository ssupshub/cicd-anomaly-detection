# CI/CD Anomaly Detection System

AI-powered anomaly detection system for CI/CD pipelines using Machine Learning. Automatically learns normal pipeline behavior and alerts when unusual patterns are detected.

## 🎯 Features

- **Automated Data Collection**: Collects metrics from Jenkins and GitHub Actions
- **ML-Powered Detection**: Uses Isolation Forest and statistical methods to detect anomalies
- **Real-time Monitoring**: Prometheus metrics with Grafana dashboards
- **Smart Alerting**: Slack, email, and webhook notifications for detected anomalies
- **REST API**: Full API for integration with existing tools
- **Automated Scheduling**: Periodic collection, training, and detection

## 🏗️ Architecture

```
┌─────────────────┐     ┌─────────────────┐
│     Jenkins     │────▶│   Collectors    │
└─────────────────┘     │                 │
                        │  - Jenkins      │
┌─────────────────┐     │  - GitHub       │
│ GitHub Actions  │────▶│  - Prometheus   │
└─────────────────┘     └────────┬────────┘
                                 │
                                 ▼
                        ┌─────────────────┐
                        │   ML Engine     │
                        │                 │
                        │ - Data Storage  │
                        │ - Anomaly Model │
                        │ - Statistics    │
                        └────────┬────────┘
                                 │
                ┌────────────────┼────────────────┐
                │                │                │
                ▼                ▼                ▼
         ┌──────────┐    ┌──────────┐    ┌──────────┐
         │   API    │    │  Alerts  │    │Prometheus│
         │  (REST)  │    │  (Slack) │    │ Exporter │
         └──────────┘    └──────────┘    └─────┬────┘
                                                │
                                                ▼
                                         ┌──────────┐
                                         │ Grafana  │
                                         │Dashboard │
                                         └──────────┘
```

## 📋 Prerequisites

- Python 3.8+
- Docker & Docker Compose (for containerized deployment)
- Jenkins (with API access) or GitHub repository
- Prometheus & Grafana (included in docker-compose)

## 🚀 Quick Start

### 1. Clone and Setup

```bash
# Clone the repository
cd cicd-anomaly-detection

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
# Copy environment template
cp .env.template .env

# Edit .env with your credentials
nano .env
```

Required configurations:
```env
# Jenkins
JENKINS_URL=http://your-jenkins-url:8080
JENKINS_USER=your-username
JENKINS_TOKEN=your-api-token

# GitHub (optional)
GITHUB_TOKEN=your-github-token
GITHUB_REPO=owner/repository

# Slack Alerts (optional)
SLACK_WEBHOOK_URL=your-slack-webhook
```

### 3. Run with Docker Compose (Recommended)

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Access services:
# - API: http://localhost:5000
# - Prometheus: http://localhost:9090
# - Grafana: http://localhost:3000 (admin/admin)
```

### 4. Run Manually

```bash
# Start API server
python api/app.py

# In another terminal, start scheduler
python scheduler.py

# In another terminal, start Prometheus exporter
python collectors/prometheus_exporter.py
```

## 📊 API Endpoints

### Health Check
```bash
curl http://localhost:5000/health
```

### Collect Metrics
```bash
curl -X POST http://localhost:5000/api/v1/collect \
  -H "Content-Type: application/json" \
  -d '{"source": "jenkins", "count": 100}'
```

### Train Model
```bash
curl -X POST http://localhost:5000/api/v1/train \
  -H "Content-Type: application/json" \
  -d '{"days": 30, "contamination": 0.1}'
```

### Detect Anomalies
```bash
curl -X POST http://localhost:5000/api/v1/detect \
  -H "Content-Type: application/json" \
  -d '{"threshold": 3.0, "send_alerts": true}'
```

### Get Recent Anomalies
```bash
curl http://localhost:5000/api/v1/anomalies?hours=24
```

### Get Status
```bash
curl http://localhost:5000/api/v1/status
```

### Run Full Pipeline
```bash
curl -X POST http://localhost:5000/api/v1/pipeline \
  -H "Content-Type: application/json" \
  -d '{"source": "jenkins"}'
```

## 🎨 Grafana Dashboard

1. Access Grafana at `http://localhost:3000`
2. Login with `admin/admin`
3. Go to Dashboards → Browse
4. Import the dashboard from `dashboards/grafana-dashboard.json`

Dashboard includes:
- Build rate by job
- Anomaly detection rate
- Build duration percentiles
- Build results distribution
- Anomaly scores
- Model accuracy and status

## 🔔 Alert Configuration

### Slack Alerts

1. Create a Slack webhook URL:
   - Go to https://api.slack.com/apps
   - Create new app → Incoming Webhooks
   - Copy webhook URL

2. Add to `.env`:
```env
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

### Email Alerts

Add to `.env`:
```env
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
ALERT_EMAIL=alerts@yourcompany.com
```

## 🧪 Testing

### Run Unit Tests
```bash
pytest tests/
```

### Test Individual Components

```bash
# Test Jenkins collector
python collectors/jenkins_collector.py

# Test GitHub collector
python collectors/github_collector.py

# Test ML model
python ml/anomaly_detector.py

# Test Prometheus exporter
python collectors/prometheus_exporter.py
```

## 📁 Project Structure

```
cicd-anomaly-detection/
├── api/
│   ├── app.py              # REST API server
│   └── alerting.py         # Alert management
├── collectors/
│   ├── jenkins_collector.py    # Jenkins metrics
│   ├── github_collector.py     # GitHub Actions metrics
│   └── prometheus_exporter.py  # Prometheus exporter
├── ml/
│   ├── anomaly_detector.py     # ML models
│   └── data_storage.py         # Data persistence
├── config/
│   ├── config.yaml             # Main configuration
│   ├── prometheus.yml          # Prometheus config
│   └── alert_rules.yml         # Alert rules
├── dashboards/
│   └── grafana-dashboard.json  # Grafana dashboard
├── tests/
│   └── test_*.py               # Unit tests
├── data/                       # Data storage (created automatically)
├── models/                     # Trained models
├── logs/                       # Application logs
├── scheduler.py                # Automated scheduler
├── docker-compose.yml          # Docker orchestration
├── Dockerfile                  # Container image
├── requirements.txt            # Python dependencies
└── README.md                   # This file
```

## 🔧 Configuration

### Model Parameters

Edit `config/config.yaml`:

```yaml
# Anomaly detection sensitivity
ANOMALY_THRESHOLD: 2.5  # Standard deviations

# Model contamination (expected anomaly rate)
MIN_TRAINING_SAMPLES: 100

# Features to monitor
FEATURES:
  - build_duration
  - test_count
  - failure_count
  - queue_time
```

### Scheduling

Default schedule (in `scheduler.py`):
- Metrics collection: Every 15 minutes
- Model training: Daily at 2 AM
- Data cleanup: Weekly on Sunday at 3 AM

## 📈 How It Works

### 1. Data Collection
- Connects to Jenkins/GitHub APIs
- Extracts build metrics (duration, failures, queue time, etc.)
- Stores in local data directory

### 2. Feature Engineering
- Normalizes metrics
- Calculates derived features (duration per test, failure rate)
- Scales data for ML algorithms

### 3. Anomaly Detection

**Isolation Forest (ML-based)**:
- Trains on historical build data
- Isolates anomalies using random partitioning
- Returns anomaly scores for new builds

**Statistical Method**:
- Calculates z-scores for each metric
- Flags values beyond threshold (default: 3σ)
- Identifies specific anomalous features

### 4. Alerting
- High-severity anomalies trigger immediate alerts
- Sends to configured channels (Slack, email)
- Includes context and recommendations

## 🐛 Troubleshooting

### Model not training
```bash
# Check if enough data collected
curl http://localhost:5000/api/v1/status

# If metrics < 100, collect more
curl -X POST http://localhost:5000/api/v1/collect \
  -H "Content-Type: application/json" \
  -d '{"source": "jenkins", "count": 200}'
```

### Connection errors
```bash
# Test Jenkins connectivity
curl -u username:token http://jenkins-url:8080/api/json

# Check logs
docker-compose logs anomaly-api
```

### No anomalies detected
- Model might need retraining with recent data
- Adjust `ANOMALY_THRESHOLD` in config
- Check if metrics are being collected

## 🔐 Security Notes

- Store credentials in `.env` file (never commit to git)
- Use API tokens, not passwords
- Limit Jenkins user permissions to read-only
- Use HTTPS for webhook URLs
- Rotate tokens regularly

## 📝 Best Practices

1. **Training Data**: Collect at least 200 builds before first training
2. **Retraining**: Retrain model weekly or after major pipeline changes
3. **Threshold Tuning**: Adjust based on false positive rate
4. **Monitoring**: Check Grafana dashboard daily
5. **Alerts**: Configure multiple channels for critical anomalies

## 🤝 Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Add tests for new features
4. Submit a pull request

## 📄 License

MIT License - see LICENSE file

## 🆘 Support

- GitHub Issues: Report bugs and request features
- Documentation: Check code comments and docstrings
- Logs: Review `logs/` directory for debugging

## 🎓 Learn More

- [Isolation Forest Algorithm](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.IsolationForest.html)
- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Tutorials](https://grafana.com/tutorials/)
- [Jenkins API](https://www.jenkins.io/doc/book/using/remote-access-api/)
- [GitHub Actions API](https://docs.github.com/en/rest/actions)

## 🎯 Roadmap

- [ ] Support for more CI/CD platforms (GitLab CI, CircleCI)
- [ ] Deep learning models (LSTM for time series)
- [ ] Automatic threshold tuning
- [ ] Root cause analysis suggestions
- [ ] Multi-tenant support
- [ ] Cloud deployment guides (AWS, GCP, Azure)
