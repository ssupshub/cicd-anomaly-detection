# Flaky Test Detection - User Guide

## Overview

The Flaky Test Detector automatically identifies tests that fail intermittently without code changes. These tests are unreliable and waste developer time, CI/CD resources, and reduce confidence in your test suite.

## What is a Flaky Test?

A flaky test is one that:
- Sometimes passes and sometimes fails
- Fails without any code changes
- Has inconsistent behavior across runs

**Common causes:**
- Race conditions and timing issues
- External dependencies (network, databases)
- Uninitialized state or shared resources
- Non-deterministic behavior
- Environmental dependencies

## How It Works

### Detection Algorithm

1. **Tracks test execution history** across all builds
2. **Calculates failure rate** for each test
3. **Identifies intermittent failures** (both passes AND failures)
4. **Computes flakiness score** based on:
   - Failure rate (40%)
   - Transition rate (40% - how often status changes)
   - Recency (20% - recent failures weighted more)

### Criteria for Flaky Tests

A test is flagged as flaky if:
- **Failure rate** >=10% (configurable)
- **Has both passes and failures** (not always failing)
- **Minimum 10 executions** in the lookback period (configurable)

## API Endpoints

### 1. Analyze Flaky Tests

Analyze test history to detect flaky tests.

**Endpoint:** `POST /api/v1/flaky-tests/analyze`

**Request:**
```bash
curl -X POST http://localhost:5000/api/v1/flaky-tests/analyze \
  -H "Content-Type: application/json" \
  -d '{"days": 30}'
```

**Response:**
```json
{
  "success": true,
  "flaky_tests_detected": 5,
  "summary": {
    "total_flaky_tests": 5,
    "by_severity": {
      "critical": 1,
      "high": 2,
      "medium": 1,
      "low": 1
    },
    "estimated_wasted_time_hours": 12.5
  },
  "flaky_tests": [...]
}
```

### 2. Get Flaky Tests List

Get currently detected flaky tests.

**Endpoint:** `GET /api/v1/flaky-tests`

**Request:**
```bash
curl http://localhost:5000/api/v1/flaky-tests
```

### 3. Get Test Details

Get detailed information about a specific flaky test.

**Endpoint:** `GET /api/v1/flaky-tests/<test_name>`

**Request:**
```bash
curl http://localhost:5000/api/v1/flaky-tests/test_user_login
```

**Response:**
```json
{
  "success": true,
  "test": {
    "test_name": "test_user_login",
    "flakiness_score": 87.5,
    "severity": "high",
    "failure_rate": 0.35,
    "total_runs": 50,
    "failures": 18,
    "passes": 32,
    "consecutive_failures": 2,
    "flip_flops": 12,
    "last_failure": "2024-02-10T14:30:00",
    "recent_history": [...],
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

## Understanding the Report

### Flakiness Score (0-100)

Higher score = more problematic

- **90-100**: Critical - Fix immediately
- **70-89**: High - Fix soon
- **50-69**: Medium - Monitor closely
- **Below 50**: Low - Minor issue

### Severity Levels

- **Critical**: Fails >50% of the time
- **High**: Fails 30-50% of the time
- **Medium**: Fails 15-30% of the time
- **Low**: Fails 10-15% of the time

### Key Metrics

**Failure Rate**
- Percentage of runs that failed
- Example: 12 failures out of 50 runs = 24%

**Flip-Flops**
- Number of times test status changed between pass/fail
- High flip-flops indicate high variability

**Consecutive Failures**
- Current streak of failures
- May indicate recent code breakage

## Recommendations

The detector provides actionable recommendations based on test patterns:

### 1. High Variability (Many Flip-Flops)

**Issue:** Test results change frequently
**Likely Cause:** Race condition or timing dependency
**Action:** Add explicit waits or synchronization
**Example Fix:**
```python
# Bad - flaky
def test_user_creation():
    create_user("test@example.com")
    user = get_user("test@example.com")  # May not be ready yet
    assert user is not None

# Good - stable
def test_user_creation():
    create_user("test@example.com")
    wait_for_condition(lambda: get_user("test@example.com"), timeout=5)
    user = get_user("test@example.com")
    assert user is not None
```

### 2. Moderate Failure Rate (20-40%)

**Issue:** Intermittent failures
**Likely Cause:** External dependency or network issue
**Action:** Add retries or mock external dependencies
**Example Fix:**
```python
# Bad - flaky
def test_api_call():
    response = requests.get("https://api.example.com/data")
    assert response.status_code == 200

# Good - stable
def test_api_call(mocker):
    mocker.patch('requests.get', return_value=Mock(status_code=200))
    response = requests.get("https://api.example.com/data")
    assert response.status_code == 200
```

### 3. High Failure Rate (>50%)

**Issue:** Frequent failures
**Likely Cause:** Test design issue or actual bug
**Action:** Review and rewrite test, or fix underlying bug
**Steps:**
1. Review test logic
2. Check if test assumptions are correct
3. Verify if actual bug exists in code
4. Rewrite test if necessary

### 4. Recent Consecutive Failures

**Issue:** Test started failing recently
**Likely Cause:** Recent code change broke test
**Action:** Review recent commits affecting this test
**Steps:**
1. Check git history for recent changes
2. Identify commits that touched tested code
3. Review those changes
4. Fix bug or update test

## Using Standalone

You can also use the detector standalone:

```python
from ml.flaky_test_detector import FlakyTestDetector

# Initialize
detector = FlakyTestDetector(
    flaky_threshold=0.1,      # 10% failure rate
    min_executions=10,         # Minimum runs to consider
    lookback_days=30          # Analyze last 30 days
)

# Record test results
for build in builds:
    detector.record_test_results(build)

# Analyze
flaky_tests = detector.analyze_flaky_tests()

# Get report for specific test
report = detector.get_flaky_test_report('test_login')
print(f"Recommendations: {report['recommendations']}")

# Save report
detector.save_report('flaky_tests_report.json')
```

## Configuration

### Environment Variables

Add to your `.env` file:

```env
# Flaky test detection thresholds
FLAKY_TEST_THRESHOLD=0.1        # 10% failure rate
FLAKY_TEST_MIN_RUNS=10          # Minimum executions
FLAKY_TEST_LOOKBACK_DAYS=30     # Days of history
```

### Adjusting Sensitivity

**More sensitive (catch more flaky tests):**
```python
detector = FlakyTestDetector(
    flaky_threshold=0.05,   # 5% failure rate
    min_executions=5
)
```

**Less sensitive (only severe cases):**
```python
detector = FlakyTestDetector(
    flaky_threshold=0.20,   # 20% failure rate
    min_executions=20
)
```

## Best Practices

### 1. Run Analysis Regularly

- Weekly analysis recommended
- After major releases
- When test suite feels unreliable

### 2. Prioritize Fixes

Fix in this order:
1. **Critical severity** tests first
2. **High flip-flop** tests (>10 transitions)
3. **Recent failures** (broke recently)
4. **High impact** tests (run frequently)

### 3. Track Improvements

Monitor these metrics over time:
- Total flaky tests
- Estimated wasted time
- Severity distribution

### 4. Prevent New Flaky Tests

- Review new tests for timing issues
- Mock external dependencies
- Use proper setup/teardown
- Avoid hardcoded waits (use explicit conditions)

## ROI Calculation

### Wasted Time

If you have 5 flaky tests that fail 30% of the time:
- Each test runs 100 times/month
- Each test takes 2 minutes
- Failures cause: 5 tests × 100 runs × 30% × 2 min = **300 minutes/month wasted**

Plus investigation time:
- Developers spend 15 minutes investigating each failure
- 5 × 100 × 30% × 15 min = **2,250 minutes/month** = **37.5 hours/month**

**Total cost:** 42.5 hours/month of developer time wasted

Fixing these 5 tests saves significant time and improves confidence in your CI/CD pipeline.

## Integration with Alerts

Flaky test detection can trigger alerts:

```python
# In scheduler or monitoring script
flaky_tests = detector.analyze_flaky_tests()

critical_flaky = [t for t in flaky_tests if t['severity'] == 'critical']

if critical_flaky:
    alert_manager.send_alert({
        'type': 'flaky_tests',
        'message': f'{len(critical_flaky)} critical flaky tests detected',
        'tests': critical_flaky
    })
```

## Troubleshooting

### No Flaky Tests Detected

**Possible reasons:**
1. Not enough test history (need 10+ runs per test)
2. Threshold too high (tests don't meet 10% failure rate)
3. Test results not being recorded properly

**Solution:** Check that `test_results` are being captured in build data

### Too Many False Positives

**Issue:** Tests flagged as flaky that aren't really flaky

**Solutions:**
- Increase `min_executions` (require more data)
- Increase `flaky_threshold` (higher failure rate required)
- Reduce `lookback_days` (focus on recent behavior)

### Missing Test Names

**Issue:** Tests not tracked individually

**Solution:** Ensure build data includes detailed test results with names:
```python
build_data = {
    'build_number': 123,
    'test_results': [
        {'name': 'test_login', 'status': 'passed'},
        {'name': 'test_signup', 'status': 'failed'}
    ]
}
```

## Example Workflow

### Daily Routine

1. **Morning:** Check flaky test dashboard
2. **Review:** Look at new flaky tests detected
3. **Triage:** Assign high-severity tests to developers
4. **Track:** Monitor fixes and improvements

### Weekly Analysis

```bash
# 1. Run analysis
curl -X POST http://localhost:5000/api/v1/flaky-tests/analyze

# 2. Get summary
curl http://localhost:5000/api/v1/flaky-tests

# 3. Get details for top offenders
curl http://localhost:5000/api/v1/flaky-tests/test_problematic_test

# 4. Create tickets for fixes
# 5. Track progress
```

---

## Summary

Flaky Test Detection helps you:
- **Identify** unreliable tests automatically
- **Understand** why tests are flaky
- **Prioritize** which tests to fix first
- **Measure** time and cost savings
- **Prevent** new flaky tests

**Result:** More reliable CI/CD, faster development, happier developers.

---

**API Version:** v2.1  
**Feature Status:** Production Ready  
**Documentation Updated:** February 2026
