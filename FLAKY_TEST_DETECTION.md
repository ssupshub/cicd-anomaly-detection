# Flaky Test Detection

## Overview

The Flaky Test Detector identifies tests that fail intermittently across builds. These tests are a major source of developer frustration because they cause CI failures unrelated to any code change, erode confidence in the test suite, and waste time on investigation.

The detector tracks every test execution across all collected builds, calculates a flakiness score for each test, and provides specific recommendations for how to fix each one.

---

## What Makes a Test Flaky

A test is classified as flaky when all three conditions are met:

1. It has both passing and failing results in the lookback period (not always failing)
2. Its failure rate is at or above the configured threshold (default: 10%)
3. It has been executed at least the minimum required number of times (default: 10)

A test that always fails is a broken test, not a flaky one. Flaky tests are specifically those with unpredictable, inconsistent behaviour.

---

## Flakiness Score

Each flaky test receives a score from 0 to 100. Higher scores indicate more severe problems.

The score is calculated from three components:

- **Failure rate (40%)**: What proportion of runs fail
- **Transition rate (40%)**: How often the result flips between pass and fail. High transitions indicate high unpredictability.
- **Recency (20%)**: Whether failures are concentrated in recent runs

---

## Severity Levels

| Severity | Failure Rate | Action |
|----------|-------------|--------|
| Critical | Above 50% | Fix immediately |
| High | 30-50% | Fix soon, assign this sprint |
| Medium | 15-30% | Schedule for next sprint |
| Low | 10-15% | Monitor and fix when capacity allows |

---

## API Usage

### Run Analysis

```bash
curl -X POST http://localhost:5000/api/v1/flaky-tests/analyze \
  -H "Content-Type: application/json" \
  -d '{"days": 30}'
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
  }
}
```

### Get Summary

```bash
curl http://localhost:5000/api/v1/flaky-tests
```

### Get Test Detail

```bash
curl http://localhost:5000/api/v1/flaky-tests/test_payment_processing
```

Response includes:
- Flakiness score and severity
- Failure rate and run counts
- Flip-flop count and consecutive failure streak
- Last failure and last pass timestamps
- Recent execution history (last 20 runs)
- Prioritised fix recommendations

---

## Recommendations

The system generates recommendations specific to the detected pattern.

### High Flip-Flop Count

Pattern: Test result changes frequently between pass and fail.
Likely cause: Race condition or timing dependency.

```python
# Problematic pattern
def test_background_job():
    trigger_job()
    result = get_job_result()   # may not be ready yet
    assert result == "completed"

# Fixed pattern
def test_background_job():
    trigger_job()
    wait_until(lambda: get_job_result() is not None, timeout=10)
    assert get_job_result() == "completed"
```

### Moderate Failure Rate (20-40%)

Pattern: Fails roughly one in four runs.
Likely cause: External dependency such as a network call or third-party service.

```python
# Problematic pattern
def test_external_api():
    response = requests.get("https://api.example.com/data")
    assert response.status_code == 200

# Fixed pattern
def test_external_api(mocker):
    mocker.patch("requests.get", return_value=Mock(status_code=200, json=lambda: {"data": []}))
    response = requests.get("https://api.example.com/data")
    assert response.status_code == 200
```

### High Failure Rate (Above 50%)

Pattern: Fails more often than it passes.
Likely cause: Test design issue or actual bug in the code under test.

Action: Review the test logic thoroughly. Verify whether a genuine bug exists. If the production code is correct, rewrite the test to be deterministic.

### Recent Consecutive Failures

Pattern: Test was passing previously but has failed on the last several runs.
Likely cause: A recent code change broke something.

Action: Review git history for commits that affect the code under test. Look for changes in the last 1-5 days.

---

## Standalone Usage

The detector can be used independently of the API:

```python
from ml.flaky_test_detector import FlakyTestDetector

detector = FlakyTestDetector(
    flaky_threshold=0.1,    # 10% failure rate
    min_executions=10,
    lookback_days=30
)

# Record test results from each build
for build in collected_builds:
    detector.record_test_results(build)

# Analyse
flaky_tests = detector.analyze_flaky_tests()

# Get recommendations for a specific test
report = detector.get_flaky_test_report("test_login")
print(report["recommendations"])

# Save full report
detector.save_report("./data/reports/flaky_tests.json")
```

Build data must include a `test_results` field:

```python
build = {
    "build_number": 123,
    "timestamp": "2026-02-17T10:00:00",
    "test_results": [
        {"name": "test_login",   "status": "passed",  "duration": 1.2},
        {"name": "test_signup",  "status": "failed",  "duration": 0.8},
        {"name": "test_payment", "status": "passed",  "duration": 2.1}
    ]
}
```

---

## Configuration

```env
# .env overrides (all optional)
FLAKY_TEST_THRESHOLD=0.1       # minimum failure rate to flag
FLAKY_TEST_MIN_RUNS=10         # minimum executions required
FLAKY_TEST_LOOKBACK_DAYS=30    # days of history to analyse
```

### Adjusting Sensitivity

More sensitive (catches more flaky tests):
```python
FlakyTestDetector(flaky_threshold=0.05, min_executions=5)
```

Less sensitive (only serious cases):
```python
FlakyTestDetector(flaky_threshold=0.20, min_executions=20)
```

---

## ROI Example

Suppose your team has 5 flaky tests with these characteristics:

- Each runs 100 times per month
- Average failure rate: 30%
- Each failure triggers a developer investigation averaging 15 minutes

Wasted developer time per month:
5 tests x 100 runs x 30% failure rate x 15 minutes = **375 hours**

Fixing all 5 tests eliminates this waste entirely. Even fixing just the 2 critical-severity tests typically recovers the majority of the wasted time.

---

## Best Practices

1. Run flaky test analysis weekly and after major releases
2. Fix critical and high severity tests within the current sprint
3. Assign flaky test fixes directly — do not let them accumulate
4. When writing new tests, mock all external dependencies and avoid hardcoded sleeps
5. Use explicit condition waits rather than fixed delays
6. Ensure test setup and teardown properly isolate shared state
