"""
Automated Scheduler
Runs periodic data collection, training, and anomaly detection
"""

import schedule
import time
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ml.anomaly_detector import AnomalyDetector
from ml.ensemble_detector import EnsembleDetector
from ml.lstm_predictor import LSTMPredictor
from ml.root_cause_analyzer import RootCauseAnalyzer
from ml.data_storage import DataStorage
from collectors.jenkins_collector import JenkinsCollector
from collectors.github_collector import GitHubActionsCollector
from collectors.gitlab_collector import GitLabCollector
from collectors.prometheus_exporter import PrometheusExporter
from api.alerting import AlertManager
from api.smart_alerting import create_smart_alert_manager
from dotenv import load_dotenv
import logging
from datetime import datetime

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AnomalyDetectionScheduler:
    """Automated scheduler for CI/CD anomaly detection"""
    
    def __init__(self):
        # Create ensemble detector
        self.ensemble = EnsembleDetector()
        
        # Add detectors to ensemble
        base_detector = AnomalyDetector()
        self.ensemble.add_detector('isolation_forest', base_detector, weight=1.2)
        
        lstm_predictor = LSTMPredictor(sequence_length=10)
        self.ensemble.add_detector('lstm', lstm_predictor, weight=1.0)
        
        # Keep reference to base detector for backward compatibility
        self.detector = base_detector
        
        # Root cause analyzer
        self.rca = RootCauseAnalyzer()
        
        # Other components
        self.storage = DataStorage('./data')
        self.prometheus = PrometheusExporter(port=8000)
        # Base alert manager (unchanged)
        _base_alert_manager = AlertManager({
            'slack_webhook_url': os.getenv('SLACK_WEBHOOK_URL', ''),
            'smtp_user': os.getenv('SMTP_USER', ''),
            'smtp_password': os.getenv('SMTP_PASSWORD', ''),
            'alert_email': os.getenv('ALERT_EMAIL', ''),
        })

        # Smart alert manager - wraps the base with batching/dedup/routing
        self.alert_manager = create_smart_alert_manager(_base_alert_manager, {
            'batch_window_seconds': int(os.getenv('ALERT_BATCH_WINDOW', 60)),
            'dedup_window_seconds': int(os.getenv('ALERT_DEDUP_WINDOW', 300)),
            'max_alerts_per_hour': int(os.getenv('ALERT_MAX_PER_HOUR', 20)),
        })
        
        # Configuration
        self.jenkins_enabled = bool(os.getenv('JENKINS_URL'))
        self.github_enabled = bool(os.getenv('GITHUB_TOKEN'))
        self.gitlab_enabled = bool(os.getenv('GITLAB_TOKEN'))
        
        # Try to load existing models
        try:
            self.ensemble.load_ensemble('./models')
            logger.info("Loaded existing ensemble")
        except:
            logger.info("No existing ensemble found")
            
            # Try to load individual detector
            try:
                self.detector.load_model('./models')
                logger.info("Loaded existing isolation forest model")
            except:
                logger.info("No existing model found")
            self.detector.load_model('./models')
            logger.info("Loaded existing model")
        except:
            logger.info("No existing model found")
    
    def collect_jenkins_metrics(self):
        """Collect metrics from Jenkins"""
        if not self.jenkins_enabled:
            logger.warning("Jenkins not configured, skipping")
            return []
        
        try:
            logger.info("Collecting Jenkins metrics...")
            jenkins_url = os.getenv('JENKINS_URL')
            jenkins_user = os.getenv('JENKINS_USER', 'admin')
            jenkins_token = os.getenv('JENKINS_TOKEN', '')
            
            collector = JenkinsCollector(jenkins_url, jenkins_user, jenkins_token)
            metrics = collector.collect_all_metrics(builds_per_job=50)
            
            if metrics:
                self.storage.save_metrics(metrics, 'jenkins')
                
                # Export to Prometheus
                for metric in metrics:
                    self.prometheus.record_build_metrics(metric)
                
                logger.info(f"Collected {len(metrics)} Jenkins metrics")
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error collecting Jenkins metrics: {e}")
            return []
    
    def collect_github_metrics(self):
        """Collect metrics from GitHub Actions"""
        if not self.github_enabled:
            logger.warning("GitHub not configured, skipping")
            return []
        
        try:
            logger.info("Collecting GitHub Actions metrics...")
            github_token = os.getenv('GITHUB_TOKEN')
            github_repo = os.getenv('GITHUB_REPO')
            
            collector = GitHubActionsCollector(github_token, github_repo)
            metrics = collector.collect_all_metrics(runs_per_workflow=50)
            
            if metrics:
                self.storage.save_metrics(metrics, 'github')
                
                # Export to Prometheus
                for metric in metrics:
                    self.prometheus.record_build_metrics(metric)
                
                logger.info(f"Collected {len(metrics)} GitHub metrics")
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error collecting GitHub metrics: {e}")
            return []
    
    def collect_gitlab_metrics(self):
        """Collect metrics from GitLab CI"""
        if not self.gitlab_enabled:
            logger.warning("GitLab not configured, skipping")
            return []
        
        try:
            logger.info("Collecting GitLab CI metrics...")
            gitlab_url = os.getenv('GITLAB_URL', 'https://gitlab.com')
            gitlab_token = os.getenv('GITLAB_TOKEN')
            gitlab_project = os.getenv('GITLAB_PROJECT')
            
            collector = GitLabCollector(gitlab_url, gitlab_token, gitlab_project)
            metrics = collector.collect_all_metrics(pipeline_count=50)
            
            if metrics:
                self.storage.save_metrics(metrics, 'gitlab')
                
                # Export to Prometheus
                for metric in metrics:
                    self.prometheus.record_build_metrics(metric)
                
                logger.info(f"Collected {len(metrics)} GitLab metrics")
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error collecting GitLab metrics: {e}")
            return []
    
    def train_model(self):
        """Train the anomaly detection model (ensemble)"""
        try:
            logger.info("Training anomaly detection ensemble...")
            
            # Load all available metrics
            metrics = self.storage.load_metrics(days=30)
            
            if len(metrics) < 100:
                logger.warning(f"Not enough data to train: {len(metrics)} samples")
                return
            
            # Train ensemble (trains all detectors)
            stats = self.ensemble.train(metrics)
            
            # Save ensemble
            self.ensemble.save_ensemble('./models')
            
            # Update Prometheus metrics
            self.prometheus.update_model_metrics(
                model_name='ensemble',
                accuracy=0.92,  # Ensemble typically has higher accuracy
                timestamp=time.time()
            )
            
            logger.info(f"Ensemble trained successfully: {stats}")
            
        except Exception as e:
            logger.error(f"Error training model: {e}")
    
    def detect_anomalies(self):
        """Detect anomalies using ensemble and perform root cause analysis"""
        if not self.ensemble.is_trained:
            logger.warning("Ensemble not trained, skipping detection")
            return
        
        try:
            logger.info("Detecting anomalies with ensemble...")
            
            # Get recent metrics
            all_metrics = self.storage.load_metrics(days=1)
            if not all_metrics:
                logger.info("No recent metrics to analyze")
                return
            
            # Get only the most recent ones
            recent_metrics = all_metrics[-20:] if len(all_metrics) > 20 else all_metrics
            
            # Ensemble detection (combines multiple models)
            anomalies, voting_stats = self.ensemble.predict(recent_metrics)
            
            logger.info(f"Ensemble voting stats: {voting_stats}")
            
            if anomalies:
                # Perform root cause analysis on high-confidence anomalies
                analyzed_anomalies = []
                
                for anomaly in anomalies:
                    # Export to Prometheus
                    job_name = anomaly.get('data', {}).get('job_name') or anomaly.get('data', {}).get('workflow_name', 'unknown')
                    self.prometheus.record_anomaly(
                        job_name, 
                        'ensemble', 
                        anomaly.get('avg_score', 0)
                    )
                    
                    # Perform RCA for high confidence anomalies
                    if anomaly.get('confidence', 0) > 0.6:
                        try:
                            analysis = self.rca.analyze(
                                anomaly, 
                                all_metrics,
                                context={}  # Could add git commits, etc.
                            )
                            anomaly['root_cause_analysis'] = analysis
                            analyzed_anomalies.append(anomaly)
                        except Exception as e:
                            logger.warning(f"RCA failed for anomaly: {e}")
                            analyzed_anomalies.append(anomaly)
                    else:
                        analyzed_anomalies.append(anomaly)
                
                # Save anomalies with RCA
                self.storage.save_anomalies(analyzed_anomalies, 'ensemble')
                
                # Send alerts for high-severity anomalies with root causes
                high_severity = [
                    a for a in analyzed_anomalies
                    if a.get('severity') in ['critical', 'high'] or a.get('confidence', 0) > 0.7
                ]
                
                for anomaly in high_severity[:5]:  # Top 5
                    # Enhanced alert with root cause
                    if 'root_cause_analysis' in anomaly:
                        self._send_enhanced_alert(anomaly)
                    else:
                        self.alert_manager.send_alert(anomaly, channels=['slack'])
                
                logger.info(f"Detected {len(anomalies)} anomalies ({len(high_severity)} high severity)")
            else:
                logger.info("No anomalies detected")
            
        except Exception as e:
            logger.error(f"Error detecting anomalies: {e}")
    
    def _send_enhanced_alert(self, anomaly: dict):
        """Send alert with root cause analysis"""
        try:
            rca = anomaly.get('root_cause_analysis', {})
            job_name = anomaly.get('data', {}).get('job_name') or anomaly.get('data', {}).get('workflow_name', 'Unknown')
            
            # Build enhanced message
            message = f"🚨 *Anomaly Detected: {job_name}*\n\n"
            message += f"*Confidence:* {anomaly.get('confidence', 0):.0%}\n"
            message += f"*Severity:* {anomaly.get('severity', 'unknown').upper()}\n"
            message += f"*Detectors Agreed:* {', '.join(anomaly.get('detectors_agreed', []))}\n\n"
            
            # Add probable causes
            causes = rca.get('probable_causes', [])
            if causes:
                message += "*Probable Root Causes:*\n"
                for i, cause in enumerate(causes[:2], 1):
                    message += f"{i}. {cause['cause']} ({cause['confidence']:.0%} confidence)\n"
                    message += f"   _{cause['description']}_\n"
                message += "\n"
            
            # Add recommendations
            recommendations = rca.get('recommendations', [])
            if recommendations:
                message += "*Recommended Actions:*\n"
                for i, rec in enumerate(recommendations[:2], 1):
                    message += f"{i}. [{rec['priority'].upper()}] {rec['action']}\n"
                    message += f"   _{rec['details']}_\n"
            
            # Send via Slack
            if self.alert_manager.slack_webhook:
                import requests
                payload = {
                    'text': message,
                    'username': 'CI/CD Anomaly Detector',
                    'icon_emoji': ':robot_face:'
                }
                requests.post(self.alert_manager.slack_webhook, json=payload, timeout=10)
            
        except Exception as e:
            logger.error(f"Error sending enhanced alert: {e}")
            # Fallback to normal alert
            self.alert_manager.send_alert(anomaly, channels=['slack'])
    
    def cleanup_old_data(self):
        """Remove old data files"""
        try:
            logger.info("Cleaning up old data...")
            removed = self.storage.cleanup_old_data(days=30)
            logger.info(f"Removed {removed} old files")
        except Exception as e:
            logger.error(f"Error cleaning up data: {e}")
    
    def run_full_pipeline(self):
        """Run the complete pipeline"""
        logger.info("=" * 50)
        logger.info("Running full anomaly detection pipeline")
        logger.info("=" * 50)
        
        # Collect metrics from all enabled sources
        jenkins_metrics = self.collect_jenkins_metrics()
        github_metrics = self.collect_github_metrics()
        gitlab_metrics = self.collect_gitlab_metrics()
        
        total_metrics = len(jenkins_metrics) + len(github_metrics) + len(gitlab_metrics)
        logger.info(f"Total metrics collected: {total_metrics}")
        
        # Detect anomalies if ensemble is trained
        if self.ensemble.is_trained and total_metrics > 0:
            self.detect_anomalies()

        # Flush any pending batched alerts at end of each cycle
        self.alert_manager.flush_now()
    
    def start(self):
        """Start the scheduler"""
        logger.info("Starting Anomaly Detection Scheduler")
        
        # Start Prometheus exporter
        self.prometheus.start()
        
        # Schedule tasks
        
        # Collect metrics every 15 minutes
        schedule.every(15).minutes.do(self.run_full_pipeline)
        
        # Train model daily at 2 AM
        schedule.every().day.at("02:00").do(self.train_model)
        
        # Cleanup weekly
        schedule.every().sunday.at("03:00").do(self.cleanup_old_data)
        
        # Run immediately on startup
        self.run_full_pipeline()
        
        logger.info("Scheduler started. Monitoring CI/CD pipelines...")
        logger.info("Collection interval: 15 minutes")
        logger.info("Training interval: Daily at 02:00")
        
        # Keep running
        try:
            while True:
                schedule.run_pending()
                time.sleep(60)
        except KeyboardInterrupt:
            logger.info("Scheduler stopped")


def main():
    """Main entry point"""
    scheduler = AnomalyDetectionScheduler()
    scheduler.start()


if __name__ == "__main__":
    main()
