"""
Smart Alert Manager
Wraps the existing AlertManager without modifying it.

New capabilities:
- Deduplication    : suppress identical alerts within a time window
- Batching         : group similar alerts into one message
- Team routing     : send different jobs to different teams/webhooks
- Maintenance windows : silence alerts during planned downtime
- Rate limiting    : prevent alert floods
- Severity filter  : only escalate alerts that meet a threshold
"""

import json
import hashlib
import time
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import logging

from api.alerting import AlertManager

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

class MaintenanceWindow:
    """A planned period during which alerts should be suppressed."""

    def __init__(self, name: str, start: datetime, end: datetime,
                 affected_jobs: Optional[List[str]] = None):
        self.name = name
        self.start = start
        self.end = end
        self.affected_jobs = affected_jobs  # None means every job

    def is_active(self) -> bool:
        return self.start <= datetime.now() <= self.end

    def affects_job(self, job_name: str) -> bool:
        if self.affected_jobs is None:
            return True
        return job_name in self.affected_jobs


class AlertRule:
    """Routing and filtering rule for a set of jobs."""

    SEVERITY_RANK = {'low': 0, 'medium': 1, 'high': 2, 'critical': 3}

    def __init__(self,
                 name: str,
                 job_pattern: Optional[str] = None,
                 min_severity: str = 'low',
                 channels: Optional[List[str]] = None,
                 team_name: Optional[str] = None,
                 slack_webhook: Optional[str] = None):
        self.name = name
        self.job_pattern = job_pattern      # substring match; None = any job
        self.min_severity = min_severity
        self.channels = channels or ['slack']
        self.team_name = team_name
        self.slack_webhook = slack_webhook  # override base webhook for this team

    def matches_job(self, job_name: str) -> bool:
        if self.job_pattern is None:
            return True
        return self.job_pattern.lower() in job_name.lower()

    def severity_passes(self, severity: str) -> bool:
        alert_rank = self.SEVERITY_RANK.get(severity.lower(), 0)
        min_rank = self.SEVERITY_RANK.get(self.min_severity.lower(), 0)
        return alert_rank >= min_rank


# ---------------------------------------------------------------------------
# SmartAlertManager
# ---------------------------------------------------------------------------

class SmartAlertManager:
    """
    Drop-in wrapper around the existing AlertManager.
    Existing call sites that use alert_manager.send_alert() continue to work
    without any change - just swap in a SmartAlertManager instance.
    """

    def __init__(self,
                 alert_manager: AlertManager,
                 batch_window_seconds: int = 60,
                 dedup_window_seconds: int = 300,
                 max_alerts_per_hour: int = 20,
                 state_file: str = './data/smart_alert_state.json'):

        # Original manager - NEVER modified
        self.alert_manager = alert_manager

        # Batching
        self.batch_window_seconds = batch_window_seconds
        self._pending_batch: List[Dict] = []
        self._batch_start_time: Optional[float] = None

        # Deduplication
        self.dedup_window_seconds = dedup_window_seconds
        self._sent_fingerprints: Dict[str, float] = {}

        # Rate limiting
        self.max_alerts_per_hour = max_alerts_per_hour
        self._alert_timestamps: List[float] = []

        # Routing rules (first match wins)
        self._rules: List[AlertRule] = []

        # Maintenance windows
        self._maintenance_windows: List[MaintenanceWindow] = []

        # State persistence path
        self.state_file = state_file

        # Statistics
        self.stats = {
            'total_received': 0,
            'total_sent': 0,
            'suppressed_duplicate': 0,
            'suppressed_maintenance': 0,
            'suppressed_rate_limit': 0,
            'suppressed_severity': 0,
            'batched': 0
        }

        self._load_state()

    # ------------------------------------------------------------------
    # Public API  (compatible with AlertManager.send_alert signature)
    # ------------------------------------------------------------------

    def send_alert(self, anomaly: Dict,
                   channels: Optional[List[str]] = None,
                   force: bool = False) -> Dict:
        """
        Send or queue an alert with smart suppression logic.

        Returns a dict describing what happened so callers can log it.
        """
        self.stats['total_received'] += 1
        job_name = self._extract_job_name(anomaly)
        severity = self._extract_severity(anomaly)

        outcome = {'sent': False, 'reason': None,
                   'job_name': job_name, 'severity': severity}

        if not force:
            # -- 1. Maintenance window check --
            if self._in_maintenance(job_name):
                self.stats['suppressed_maintenance'] += 1
                outcome['reason'] = 'maintenance_window'
                logger.info(f"Alert suppressed (maintenance): {job_name}")
                self._save_state()
                return outcome

            # -- 2. Deduplication check --
            fp = self._fingerprint(anomaly)
            if self._is_duplicate(fp):
                self.stats['suppressed_duplicate'] += 1
                outcome['reason'] = 'duplicate'
                logger.info(f"Alert suppressed (duplicate): {job_name}")
                self._save_state()
                return outcome

            # -- 3. Rate limit check --
            if self._is_rate_limited():
                self.stats['suppressed_rate_limit'] += 1
                outcome['reason'] = 'rate_limit'
                logger.warning(f"Alert suppressed (rate limit): {job_name}")
                self._save_state()
                return outcome

            # -- 4. Resolve routing rule --
            rule = self._resolve_rule(job_name)

            # -- 5. Severity threshold check --
            if rule and not rule.severity_passes(severity):
                self.stats['suppressed_severity'] += 1
                outcome['reason'] = 'below_severity_threshold'
                logger.info(f"Alert suppressed (severity {severity} < {rule.min_severity}): {job_name}")
                self._save_state()
                return outcome

            # -- 6. Determine channels --
            if channels is None:
                channels = rule.channels if rule else ['slack']

            # -- 7. Use team-specific manager if rule defines one --
            effective_manager = self._get_effective_manager(rule)

            # -- 8. Record fingerprint now (before flush to count this send) --
            self._record_sent(fp)

        else:
            # force=True skips all suppression
            effective_manager = self.alert_manager
            if channels is None:
                channels = ['slack', 'email']

        # -- 9. Queue into batch --
        self._add_to_batch(anomaly)

        # -- 10. Flush batch if window has elapsed --
        if self._should_flush_batch():
            ok = self._flush_batch(effective_manager, channels)
            outcome['sent'] = ok
            outcome['reason'] = 'batch_flushed'
        else:
            outcome['sent'] = False
            outcome['reason'] = 'queued_in_batch'
            logger.info(f"Alert queued ({len(self._pending_batch)} pending): {job_name}")

        self._save_state()
        return outcome

    def flush_now(self, channels: Optional[List[str]] = None) -> bool:
        """
        Immediately send all pending batched alerts.
        Call this at the end of each scheduler detection cycle so no
        alerts are silently lost if the batch window has not elapsed.
        """
        if not self._pending_batch:
            return True
        rule = self._resolve_rule(self._extract_job_name(self._pending_batch[0]))
        effective_manager = self._get_effective_manager(rule)
        if channels is None:
            channels = rule.channels if rule else ['slack']
        return self._flush_batch(effective_manager, channels)

    # ------------------------------------------------------------------
    # Rule management
    # ------------------------------------------------------------------

    def add_rule(self, rule: AlertRule):
        """Add a routing rule. Evaluated in insertion order; first match wins."""
        self._rules.append(rule)
        logger.info(f"Added alert rule: {rule.name}")

    def remove_rule(self, name: str):
        self._rules = [r for r in self._rules if r.name != name]

    def list_rules(self) -> List[Dict]:
        return [
            {
                'name': r.name,
                'job_pattern': r.job_pattern,
                'min_severity': r.min_severity,
                'channels': r.channels,
                'team_name': r.team_name
            }
            for r in self._rules
        ]

    # ------------------------------------------------------------------
    # Maintenance window management
    # ------------------------------------------------------------------

    def add_maintenance_window(self, window: MaintenanceWindow):
        self._maintenance_windows.append(window)
        logger.info(f"Added maintenance window: {window.name}")

    def remove_maintenance_window(self, name: str):
        self._maintenance_windows = [
            w for w in self._maintenance_windows if w.name != name
        ]

    def list_active_windows(self) -> List[Dict]:
        return [
            {
                'name': w.name,
                'start': w.start.isoformat(),
                'end': w.end.isoformat(),
                'affected_jobs': w.affected_jobs
            }
            for w in self._maintenance_windows if w.is_active()
        ]

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        suppressed = (
            self.stats['suppressed_duplicate'] +
            self.stats['suppressed_maintenance'] +
            self.stats['suppressed_rate_limit'] +
            self.stats['suppressed_severity']
        )
        return {
            **self.stats,
            'total_suppressed': suppressed,
            'suppression_rate': suppressed / max(self.stats['total_received'], 1),
            'pending_in_batch': len(self._pending_batch),
            'active_maintenance_windows': len(self.list_active_windows()),
            'registered_rules': len(self._rules),
            'alerts_last_hour': self._count_alerts_last_hour()
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _extract_job_name(self, anomaly: Dict) -> str:
        data = anomaly.get('data', {})
        return data.get('job_name') or data.get('workflow_name', 'unknown')

    def _extract_severity(self, anomaly: Dict) -> str:
        if 'severity' in anomaly:
            return anomaly['severity']
        z = anomaly.get('max_z_score', 0)
        if z > 5:
            return 'critical'
        if z > 4:
            return 'high'
        if z > 2.5:
            return 'medium'
        return 'low'

    def _fingerprint(self, anomaly: Dict) -> str:
        job = self._extract_job_name(anomaly)
        features = sorted(f['feature'] for f in anomaly.get('anomaly_features', []))
        raw = f"{job}|{'|'.join(features)}"
        return hashlib.md5(raw.encode()).hexdigest()

    def _is_duplicate(self, fingerprint: str) -> bool:
        last = self._sent_fingerprints.get(fingerprint)
        if last is None:
            return False
        return (time.time() - last) < self.dedup_window_seconds

    def _record_sent(self, fingerprint: str):
        self._sent_fingerprints[fingerprint] = time.time()
        # Prune stale entries
        cutoff = time.time() - self.dedup_window_seconds
        self._sent_fingerprints = {
            k: v for k, v in self._sent_fingerprints.items() if v > cutoff
        }

    def _is_rate_limited(self) -> bool:
        self._alert_timestamps = [
            t for t in self._alert_timestamps if time.time() - t < 3600
        ]
        return len(self._alert_timestamps) >= self.max_alerts_per_hour

    def _count_alerts_last_hour(self) -> int:
        return len([t for t in self._alert_timestamps if time.time() - t < 3600])

    def _in_maintenance(self, job_name: str) -> bool:
        return any(
            w.is_active() and w.affects_job(job_name)
            for w in self._maintenance_windows
        )

    def _resolve_rule(self, job_name: str) -> Optional[AlertRule]:
        for rule in self._rules:
            if rule.matches_job(job_name):
                return rule
        return None

    def _get_effective_manager(self,
                               rule: Optional[AlertRule]) -> AlertManager:
        """
        Return a manager configured for the rule's team webhook.
        Creates a new AlertManager if override needed - never mutates the original.
        """
        if rule and rule.slack_webhook:
            override = dict(self.alert_manager.config)
            override['slack_webhook_url'] = rule.slack_webhook
            return AlertManager(override)
        return self.alert_manager

    def _add_to_batch(self, anomaly: Dict):
        if self._batch_start_time is None:
            self._batch_start_time = time.time()
        self._pending_batch.append(anomaly)
        self.stats['batched'] += 1

    def _should_flush_batch(self) -> bool:
        if not self._pending_batch or self._batch_start_time is None:
            return False
        return (time.time() - self._batch_start_time) >= self.batch_window_seconds

    def _flush_batch(self, manager: AlertManager,
                     channels: List[str]) -> bool:
        if not self._pending_batch:
            return True

        batch = self._pending_batch.copy()
        self._pending_batch = []
        self._batch_start_time = None

        self._alert_timestamps.append(time.time())
        self.stats['total_sent'] += 1

        if len(batch) == 1:
            result = manager.send_alert(batch[0], channels=channels)
            logger.info(f"Sent 1 alert: {self._extract_job_name(batch[0])}")
            return bool(result)
        else:
            result = manager.send_batch_alert(batch)
            logger.info(f"Sent batch of {len(batch)} alerts")
            return bool(result)

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def _save_state(self):
        try:
            os.makedirs(os.path.dirname(self.state_file) or '.', exist_ok=True)
            state = {
                'fingerprints': self._sent_fingerprints,
                'alert_timestamps': self._alert_timestamps,
                'stats': self.stats
            }
            with open(self.state_file, 'w') as f:
                json.dump(state, f)
        except Exception as e:
            logger.warning(f"Could not save smart alert state: {e}")

    def _load_state(self):
        try:
            if not os.path.exists(self.state_file):
                return
            with open(self.state_file) as f:
                state = json.load(f)
            self._sent_fingerprints = state.get('fingerprints', {})
            self._alert_timestamps = state.get('alert_timestamps', [])
            saved_stats = state.get('stats', {})
            self.stats.update(saved_stats)
            logger.info("Loaded smart alert state from disk")
        except Exception as e:
            logger.warning(f"Could not load smart alert state: {e}")


# ---------------------------------------------------------------------------
# Convenience factory
# ---------------------------------------------------------------------------

def create_smart_alert_manager(alert_manager: AlertManager,
                               config: Optional[Dict] = None) -> SmartAlertManager:
    """
    Build a SmartAlertManager from a plain config dict.

    config keys:
        batch_window_seconds   int   (default 60)
        dedup_window_seconds   int   (default 300)
        max_alerts_per_hour    int   (default 20)
        rules                  list  of rule dicts
        maintenance_windows    list  of window dicts
    """
    cfg = config or {}

    smart = SmartAlertManager(
        alert_manager=alert_manager,
        batch_window_seconds=cfg.get('batch_window_seconds', 60),
        dedup_window_seconds=cfg.get('dedup_window_seconds', 300),
        max_alerts_per_hour=cfg.get('max_alerts_per_hour', 20)
    )

    for r in cfg.get('rules', []):
        smart.add_rule(AlertRule(
            name=r['name'],
            job_pattern=r.get('job_pattern'),
            min_severity=r.get('min_severity', 'low'),
            channels=r.get('channels', ['slack']),
            team_name=r.get('team_name'),
            slack_webhook=r.get('slack_webhook')
        ))

    for w in cfg.get('maintenance_windows', []):
        smart.add_maintenance_window(MaintenanceWindow(
            name=w['name'],
            start=datetime.fromisoformat(w['start']),
            end=datetime.fromisoformat(w['end']),
            affected_jobs=w.get('affected_jobs')
        ))

    return smart


# ---------------------------------------------------------------------------
# Standalone demo
# ---------------------------------------------------------------------------

def main():
    import os
    from dotenv import load_dotenv
    load_dotenv()

    base_manager = AlertManager({
        'slack_webhook_url': os.getenv('SLACK_WEBHOOK_URL', ''),
        'smtp_user': os.getenv('SMTP_USER', ''),
        'smtp_password': os.getenv('SMTP_PASSWORD', ''),
        'alert_email': os.getenv('ALERT_EMAIL', ''),
    })

    smart = create_smart_alert_manager(base_manager, {
        'batch_window_seconds': 3,
        'dedup_window_seconds': 30,
        'max_alerts_per_hour': 20,
        'rules': [
            {
                'name': 'frontend-team',
                'job_pattern': 'frontend',
                'min_severity': 'medium',
                'channels': ['slack'],
                'team_name': 'Frontend'
            },
            {
                'name': 'production-oncall',
                'job_pattern': 'deploy-prod',
                'min_severity': 'high',
                'channels': ['slack', 'email'],
                'team_name': 'On-Call'
            },
            {
                'name': 'default',
                'job_pattern': None,
                'min_severity': 'medium',
                'channels': ['slack']
            }
        ]
    })

    # Add maintenance window for staging
    smart.add_maintenance_window(MaintenanceWindow(
        name='staging-deploy',
        start=datetime.now() - timedelta(minutes=1),
        end=datetime.now() + timedelta(hours=2),
        affected_jobs=['deploy-staging']
    ))

    def anomaly(job, severity='high', z=4.5):
        return {
            'severity': severity,
            'max_z_score': z,
            'data': {'job_name': job, 'duration': 800},
            'anomaly_features': [
                {'feature': 'duration', 'value': 800, 'expected': 300, 'z_score': z}
            ]
        }

    cases = [
        ('deploy-staging',  'high',   'Suppressed - maintenance window'),
        ('build-frontend',  'low',    'Suppressed - below severity threshold'),
        ('build-frontend',  'medium', 'Queued in batch - frontend rule'),
        ('deploy-prod',     'high',   'Queued in batch - on-call rule'),
        ('deploy-prod',     'high',   'Suppressed - duplicate'),
        ('build-api',       'medium', 'Queued in batch - default rule'),
    ]

    print("=" * 60)
    print("SMART ALERTING DEMO")
    print("=" * 60)

    for job, sev, note in cases:
        result = smart.send_alert(anomaly(job, sev))
        print(f"  {note}")
        print(f"  -> job={job} sev={sev} sent={result['sent']} reason={result['reason']}\n")

    time.sleep(3)
    print("--- Flushing batch ---")
    smart.flush_now()

    print("\n" + "=" * 60)
    print("STATISTICS")
    print("=" * 60)
    for k, v in smart.get_stats().items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
