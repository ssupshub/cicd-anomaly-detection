# API Documentation

## Base URL
```
http://localhost:5000
```

## Authentication
Currently no authentication required. For production, implement API key authentication.

## Endpoints

### Health Check

Check if the API is running.

**Endpoint:** `GET /health`

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2024-02-08T12:00:00",
  "model_trained": true
}
```

---

### Collect Metrics

Collect metrics from Jenkins or GitHub Actions.

**Endpoint:** `POST /api/v1/collect`

**Request Body:**
```json
{
  "source": "jenkins",  // or "github"
  "count": 100          // number of builds to collect
}
```

**Response:**
```json
{
  "success": true,
  "metrics_collected": 150,
  "source": "jenkins",
  "filepath": "./data/metrics/jenkins_20240208_120000.json"
}
```

**Example:**
```bash
curl -X POST http://localhost:5000/api/v1/collect \
  -H "Content-Type: application/json" \
  -d '{"source": "jenkins", "count": 100}'
```

---

### Train Model

Train the anomaly detection model on historical data.

**Endpoint:** `POST /api/v1/train`

**Request Body:**
```json
{
  "days": 30,              // days of data to use
  "contamination": 0.1     // expected anomaly rate (0.0 - 0.5)
}
```

**Response:**
```json
{
  "success": true,
  "training_stats": {
    "samples": 500,
    "features": 8,
    "anomalies_detected": 50,
    "anomaly_rate": 0.1,
    "trained_at": "2024-02-08T12:00:00"
  }
}
```

**Example:**
```bash
curl -X POST http://localhost:5000/api/v1/train \
  -H "Content-Type: application/json" \
  -d '{"days": 30, "contamination": 0.1}'
```

---

### Detect Anomalies

Detect anomalies in metrics.

**Endpoint:** `POST /api/v1/detect`

**Request Body:**
```json
{
  "metrics": [],           // optional: provide specific metrics
  "threshold": 3.0,        // z-score threshold for statistical detection
  "send_alerts": true      // whether to send alerts
}
```

**Response:**
```json
{
  "success": true,
  "total_samples": 100,
  "ml_anomalies": 5,
  "statistical_anomalies": 3,
  "anomalies": [
    {
      "index": 0,
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
        "result": "SUCCESS"
      }
    }
  ],
  "anomaly_rate": 0.08
}
```

**Example:**
```bash
curl -X POST http://localhost:5000/api/v1/detect \
  -H "Content-Type: application/json" \
  -d '{"threshold": 3.0, "send_alerts": true}'
```

---

### Get Recent Anomalies

Retrieve recently detected anomalies.

**Endpoint:** `GET /api/v1/anomalies?hours=24`

**Query Parameters:**
- `hours` (optional): Number of hours to look back (default: 24)

**Response:**
```json
{
  "success": true,
  "count": 10,
  "period_hours": 24,
  "anomalies": [
    {
      "index": 5,
      "max_z_score": 3.8,
      "data": {
        "job_name": "test-suite",
        "duration": 500.0
      }
    }
  ]
}
```

**Example:**
```bash
curl http://localhost:5000/api/v1/anomalies?hours=48
```

---

### Get Report

Generate a summary report of metrics and anomalies.

**Endpoint:** `GET /api/v1/report`

**Response:**
```json
{
  "generated_at": "2024-02-08T12:00:00",
  "period": "7 days",
  "total_metrics": 1000,
  "total_anomalies": 50,
  "anomaly_rate": 0.05,
  "avg_duration": 250.5,
  "max_duration": 800.0,
  "result_distribution": {
    "SUCCESS": 900,
    "FAILURE": 100
  },
  "failure_rate": 0.1,
  "total_jobs": 5,
  "builds_per_job": 200.0
}
```

**Example:**
```bash
curl http://localhost:5000/api/v1/report
```

---

### Get System Status

Get current system status and metrics.

**Endpoint:** `GET /api/v1/status`

**Response:**
```json
{
  "model_trained": true,
  "features": [
    "duration",
    "queue_time",
    "test_count",
    "failure_count"
  ],
  "total_metrics": 1000,
  "total_anomalies": 50,
  "anomaly_rate": 0.05,
  "last_updated": "2024-02-08T12:00:00"
}
```

**Example:**
```bash
curl http://localhost:5000/api/v1/status
```

---

### Run Full Pipeline

Execute the complete data collection, training, and detection pipeline.

**Endpoint:** `POST /api/v1/pipeline`

**Request Body:**
```json
{
  "source": "jenkins"  // or "github"
}
```

**Response:**
```json
{
  "success": true,
  "metrics_collected": 200,
  "training_stats": {
    "samples": 500,
    "features": 8,
    "anomalies_detected": 50
  },
  "anomalies_detected": 15
}
```

**Example:**
```bash
curl -X POST http://localhost:5000/api/v1/pipeline \
  -H "Content-Type: application/json" \
  -d '{"source": "jenkins"}'
```

---

## Error Responses

All endpoints may return error responses:

**400 Bad Request:**
```json
{
  "error": "Invalid parameter: source must be 'jenkins' or 'github'"
}
```

**500 Internal Server Error:**
```json
{
  "error": "Failed to connect to Jenkins server"
}
```

---

## Prometheus Metrics

The system exposes Prometheus metrics on port 8000:

**Endpoint:** `http://localhost:8000/metrics`

**Available Metrics:**
- `cicd_build_duration_seconds` - Build duration histogram
- `cicd_build_total` - Total build count by result
- `cicd_queue_time_seconds` - Queue time histogram
- `cicd_test_count` - Number of tests
- `cicd_failure_count` - Number of failures
- `cicd_anomaly_score` - Anomaly score gauge
- `cicd_anomaly_total` - Total anomalies detected
- `cicd_model_accuracy` - Model accuracy
- `cicd_model_last_trained_timestamp` - Last training timestamp
- `cicd_active_jobs` - Number of active jobs
- `cicd_data_points_total` - Total data points collected

---

## Rate Limiting

No rate limiting currently implemented. For production deployment, consider implementing rate limiting based on IP or API key.

---

## WebSocket Support

WebSocket support for real-time anomaly notifications is planned for future versions.

---

## Best Practices

1. **Initial Setup:**
   - Collect at least 100-200 builds before training
   - Use 30 days of data for initial training

2. **Regular Operations:**
   - Retrain model weekly or after significant pipeline changes
   - Monitor anomaly rate (should be 5-15%)
   - Adjust threshold based on false positive rate

3. **Performance:**
   - Batch collect metrics (50-100 at a time)
   - Cache model predictions for identical metrics
   - Use async processing for large datasets

4. **Security:**
   - Use HTTPS in production
   - Implement API authentication
   - Restrict access to sensitive endpoints
   - Rotate credentials regularly
