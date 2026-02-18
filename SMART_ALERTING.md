# Smart Alerting

## Overview

The Smart Alert Manager is a wrapper layer that sits in front of the base AlertManager. It adds five capabilities — deduplication, batching, team routing, maintenance windows, and rate limiting — without modifying any existing alerting code. All existing call sites continue to work identically.

---

## How It Works

When an anomaly is detected, the smart layer evaluates it against five rules in sequence before deciding whether to send an alert:

```
Anomaly received
      |
      v
1. Maintenance window check --> suppressed if active
      |
      v
2. Deduplication check ------> suppressed if same fingerprint seen recently
      |
      v
3. Rate limit check ----------> suppressed if hourly cap reached
      |
      v
4. Routing rule match -------> first matching rule selected
      |
      v
5. Severity threshold check --> suppressed if below rule minimum
      |
      v
6. Add to batch buffer
      |
      v
7. Batch window elapsed? -----> no: wait
                         |
                        yes
                         |
                         v
                  Send batch to channel(s)
                  Record fingerprint and timestamp
```

---

## Feature Reference

### Deduplication

The system creates a fingerprint from the job name and the set of anomalous features. If an identical fingerprint was sent within the dedup window, the alert is suppressed.

Default window: 5 minutes. Configurable via `ALERT_DEDUP_WINDOW`.

This prevents ten identical "build-api duration is high" alerts arriving during a sustained incident. One alert is sent; subsequent duplicates are silent.

### Batching

Alerts are collected in a buffer. When the batch window elapses, all buffered alerts are sent as one message using the existing `send_batch_alert` format.

Default window: 60 seconds. Configurable via `ALERT_BATCH_WINDOW`.

If only one alert is buffered, it is sent using the standard single-alert format.

The scheduler calls `flush_now()` at the end of each detection cycle to ensure no alerts are held indefinitely.

### Team Routing

Rules are evaluated in insertion order. The first matching rule determines where the alert goes.

Each rule specifies:
- A job name pattern (substring match)
- A minimum severity threshold
- The delivery channels
- An optional team-specific Slack webhook

If no rule matches, the default channels are used.

### Maintenance Windows

A maintenance window has a name, a start time, an end time, and an optional list of affected job names. If no job names are specified, all jobs are covered.

During an active window, all alerts for covered jobs are suppressed silently. The window is registered and removed via the API.

### Rate Limiting

A per-hour counter tracks how many alerts have been sent. Once the limit is reached, further alerts are suppressed until the oldest timestamp in the window drops off.

Default limit: 20 per hour. Configurable via `ALERT_MAX_PER_HOUR`.

---

## Configuration

### Environment Variables

```env
ALERT_BATCH_WINDOW=60        # seconds to collect before sending
ALERT_DEDUP_WINDOW=300       # seconds to suppress duplicates
ALERT_MAX_PER_HOUR=20        # hard cap on alerts per hour
```

### State Persistence

Deduplication fingerprints, rate limit timestamps, and statistics are written to `./data/smart_alert_state.json` after every decision. If the process restarts, the state is reloaded automatically and suppression continues correctly.

---

## API Reference

### Rules

**GET /api/v1/alerts/rules** — List all rules

**POST /api/v1/alerts/rules** — Add a rule

```json
{
  "name": "frontend-team",
  "job_pattern": "frontend",
  "min_severity": "medium",
  "channels": ["slack"],
  "team_name": "Frontend",
  "slack_webhook": "https://hooks.slack.com/services/FRONTEND/CHANNEL"
}
```

Field notes:
- `job_pattern`: Substring match against job name. Omit to match all jobs.
- `min_severity`: One of `low`, `medium`, `high`, `critical`. Alerts below this level are suppressed.
- `channels`: Any combination of `slack`, `email`, `webhook`.
- `slack_webhook`: If set, overrides the default Slack webhook for this team only.

**DELETE /api/v1/alerts/rules/{name}** — Remove a rule

### Maintenance Windows

**GET /api/v1/alerts/maintenance** — List active windows

**POST /api/v1/alerts/maintenance** — Add a window

```json
{
  "name": "weekly-deploy",
  "start": "2026-02-18T02:00:00",
  "end":   "2026-02-18T04:00:00",
  "affected_jobs": ["deploy-prod", "deploy-staging"]
}
```

Omit `affected_jobs` to suppress all jobs during the window.

**DELETE /api/v1/alerts/maintenance/{name}** — Remove a window

### Statistics

**GET /api/v1/alerts/stats**

```json
{
  "total_received": 120,
  "total_sent": 18,
  "suppressed_duplicate": 45,
  "suppressed_maintenance": 12,
  "suppressed_rate_limit": 5,
  "suppressed_severity": 40,
  "total_suppressed": 102,
  "suppression_rate": 0.85,
  "pending_in_batch": 0,
  "active_maintenance_windows": 1,
  "registered_rules": 3,
  "alerts_last_hour": 4
}
```

**POST /api/v1/alerts/flush** — Send all pending batched alerts immediately

---

## Common Routing Configurations

### By Environment

```json
[
  { "name": "prod",    "job_pattern": "prod",    "min_severity": "high",   "channels": ["slack", "email"] },
  { "name": "staging", "job_pattern": "staging", "min_severity": "high",   "channels": ["slack"] },
  { "name": "default", "job_pattern": null,       "min_severity": "medium", "channels": ["slack"] }
]
```

### By Team

```json
[
  { "name": "frontend",  "job_pattern": "frontend",  "min_severity": "medium", "slack_webhook": "FRONTEND_WEBHOOK" },
  { "name": "backend",   "job_pattern": "backend",   "min_severity": "medium", "slack_webhook": "BACKEND_WEBHOOK" },
  { "name": "platform",  "job_pattern": "infra",     "min_severity": "low",    "slack_webhook": "PLATFORM_WEBHOOK" },
  { "name": "default",   "job_pattern": null,         "min_severity": "high",   "channels": ["slack"] }
]
```

### Critical Alerts to PagerDuty via Webhook

```json
[
  {
    "name": "oncall-critical",
    "job_pattern": "deploy-prod",
    "min_severity": "critical",
    "channels": ["slack", "webhook"]
  }
]
```

---

## Programmatic Usage

```python
from api.alerting import AlertManager
from api.smart_alerting import SmartAlertManager, AlertRule, MaintenanceWindow, create_smart_alert_manager
from datetime import datetime, timedelta

base = AlertManager(config)

smart = create_smart_alert_manager(base, {
    "batch_window_seconds": 60,
    "dedup_window_seconds": 300,
    "max_alerts_per_hour": 20,
    "rules": [
        {
            "name": "prod-oncall",
            "job_pattern": "deploy-prod",
            "min_severity": "high",
            "channels": ["slack", "email"]
        }
    ]
})

# Add a maintenance window
smart.add_maintenance_window(MaintenanceWindow(
    name="deploy-window",
    start=datetime.now(),
    end=datetime.now() + timedelta(hours=2),
    affected_jobs=["deploy-prod"]
))

# Send an alert (same interface as AlertManager.send_alert)
result = smart.send_alert(anomaly)
# result: {"sent": bool, "reason": str, "job_name": str, "severity": str}

# Force-flush the batch
smart.flush_now()

# Check statistics
stats = smart.get_stats()
```

The `send_alert` method is fully compatible with the existing `AlertManager.send_alert` signature. Swapping in a `SmartAlertManager` instance requires no other code changes.

---

## Severity Reference

| Severity | z-score | When to use |
|----------|---------|-------------|
| low | Below 2.5 | Informational only |
| medium | 2.5-4.0 | Worth investigating |
| high | 4.0-5.0 | Needs prompt attention |
| critical | Above 5.0 | Immediate response required |

Severity can also be set explicitly in the anomaly dict:

```python
anomaly = {
    "severity": "high",
    "data": {"job_name": "build-api"},
    ...
}
```

If `severity` is absent, it is derived from `max_z_score`.
