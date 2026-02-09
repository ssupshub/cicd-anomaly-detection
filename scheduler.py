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
from ml.data_storage import DataStorage
from collectors.jenkins_collector import JenkinsCollector
from collectors.github_collector import GitHubActionsCollector
from collectors.prometheus_exporter import PrometheusExporter
from api.alerting import AlertManager
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
        self.detector = AnomalyDetector()
        self.storage = DataStorage('./data')
        self.prometheus = PrometheusExporter(port=8000)
        self.alert_manager = AlertManager({
            'slack_webhook_url': os.getenv('SLACK_WEBHOOK_URL', ''),
            'smtp_user': os.getenv('SMTP_USER', ''),
            'smtp_password': os.getenv('SMTP_PASSWORD', ''),
            'alert_email': os.getenv('ALERT_EMAIL', ''),
        })
        
        # Configuration
        self.jenkins_enabled = bool(os.getenv('JENKINS_URL'))
        self.github_enabled = bool(os.getenv('GITHUB_TOKEN'))
        
        # Try to load existing model
        try:
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
    
    def train_model(self):
        """Train the anomaly detection model"""
        try:
            logger.info("Training anomaly detection model...")
            
            # Load all available metrics
            metrics = self.storage.load_metrics(days=30)
            
            if len(metrics) < 100:
                logger.warning(f"Not enough data to train: {len(metrics)} samples")
                return
            
            # Train model
            stats = self.detector.train(metrics)
            
            # Save model
            self.detector.save_model('./models')
            
            # Update Prometheus metrics
            self.prometheus.update_model_metrics(
                model_name='isolation_forest',
                accuracy=0.95,  # Placeholder
                timestamp=time.time()
            )
            
            logger.info(f"Model trained successfully: {stats}")
            
        except Exception as e:
            logger.error(f"Error training model: {e}")
    
    def detect_anomalies(self):
        """Detect anomalies in recent metrics"""
        if not self.detector.is_trained:
            logger.warning("Model not trained, skipping detection")
            return
        
        try:
            logger.info("Detecting anomalies...")
            
            # Get recent metrics (last hour)
            all_metrics = self.storage.load_metrics(days=1)
            if not all_metrics:
                logger.info("No recent metrics to analyze")
                return
            
            # Get only the most recent ones (e.g., last 20)
            recent_metrics = all_metrics[-20:] if len(all_metrics) > 20 else all_metrics
            
            # ML-based detection
            predictions, scores = self.detector.predict(recent_metrics)
            
            # Statistical detection
            stat_anomalies = self.detector.detect_statistical_anomalies(
                recent_metrics,
                threshold=2.5
            )
            
            # Collect anomalies
            ml_anomalies = []
            for i, (pred, score) in enumerate(zip(predictions, scores)):
                if pred == -1:
                    anomaly = {
                        'index': i,
                        'score': float(score),
                        'data': recent_metrics[i],
                        'detection_method': 'ml'
                    }
                    ml_anomalies.append(anomaly)
                    
                    # Export to Prometheus
                    job_name = recent_metrics[i].get('job_name') or recent_metrics[i].get('workflow_name', 'unknown')
                    self.prometheus.record_anomaly(job_name, 'ml', abs(score))
            
            # Process statistical anomalies
            for anomaly in stat_anomalies:
                anomaly['detection_method'] = 'statistical'
                job_name = anomaly.get('data', {}).get('job_name') or anomaly.get('data', {}).get('workflow_name', 'unknown')
                self.prometheus.record_anomaly(job_name, 'statistical', anomaly.get('max_z_score', 0))
            
            all_anomalies = ml_anomalies + stat_anomalies
            
            if all_anomalies:
                # Save anomalies
                self.storage.save_anomalies(all_anomalies)
                
                # Send alerts for high-severity anomalies
                high_severity = [
                    a for a in all_anomalies
                    if a.get('max_z_score', 0) > 3.5 or abs(a.get('score', 0)) > 0.5
                ]
                
                for anomaly in high_severity[:5]:  # Top 5
                    self.alert_manager.send_alert(anomaly, channels=['slack'])
                
                logger.info(f"Detected {len(all_anomalies)} anomalies ({len(high_severity)} high severity)")
            else:
                logger.info("No anomalies detected")
            
        except Exception as e:
            logger.error(f"Error detecting anomalies: {e}")
    
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
        
        # Collect metrics
        jenkins_metrics = self.collect_jenkins_metrics()
        github_metrics = self.collect_github_metrics()
        
        total_metrics = len(jenkins_metrics) + len(github_metrics)
        logger.info(f"Total metrics collected: {total_metrics}")
        
        # Detect anomalies if model is trained
        if self.detector.is_trained and total_metrics > 0:
            self.detect_anomalies()
    
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
