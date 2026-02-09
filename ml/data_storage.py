"""
Data Storage Manager
Handles persistent storage of metrics and anomaly detection results
"""

import json
import os
import pandas as pd
from datetime import datetime
from typing import List, Dict, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DataStorage:
    """Manages storage of CI/CD metrics and anomaly detection results"""
    
    def __init__(self, data_dir: str = './data'):
        self.data_dir = data_dir
        self.metrics_dir = os.path.join(data_dir, 'metrics')
        self.anomalies_dir = os.path.join(data_dir, 'anomalies')
        self.reports_dir = os.path.join(data_dir, 'reports')
        
        self._create_directories()
    
    def _create_directories(self):
        """Create necessary directories"""
        for directory in [self.metrics_dir, self.anomalies_dir, self.reports_dir]:
            os.makedirs(directory, exist_ok=True)
    
    def save_metrics(self, metrics: List[Dict], source: str = 'unknown'):
        """Save collected metrics to JSON file"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{source}_{timestamp}.json"
        filepath = os.path.join(self.metrics_dir, filename)
        
        with open(filepath, 'w') as f:
            json.dump(metrics, f, indent=2)
        
        logger.info(f"Saved {len(metrics)} metrics to {filepath}")
        return filepath
    
    def load_metrics(self, source: Optional[str] = None, days: int = 30) -> List[Dict]:
        """Load metrics from storage"""
        all_metrics = []
        
        for filename in os.listdir(self.metrics_dir):
            if not filename.endswith('.json'):
                continue
            
            if source and not filename.startswith(source):
                continue
            
            filepath = os.path.join(self.metrics_dir, filename)
            
            # Check file age
            file_time = datetime.fromtimestamp(os.path.getmtime(filepath))
            age_days = (datetime.now() - file_time).days
            
            if age_days > days:
                continue
            
            with open(filepath, 'r') as f:
                metrics = json.load(f)
                all_metrics.extend(metrics)
        
        logger.info(f"Loaded {len(all_metrics)} metrics from storage")
        return all_metrics
    
    def save_anomalies(self, anomalies: List[Dict], detection_type: str = 'ml'):
        """Save detected anomalies"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"anomalies_{detection_type}_{timestamp}.json"
        filepath = os.path.join(self.anomalies_dir, filename)
        
        with open(filepath, 'w') as f:
            json.dump(anomalies, f, indent=2)
        
        logger.info(f"Saved {len(anomalies)} anomalies to {filepath}")
        return filepath
    
    def load_recent_anomalies(self, hours: int = 24) -> List[Dict]:
        """Load anomalies from recent hours"""
        all_anomalies = []
        cutoff_time = datetime.now().timestamp() - (hours * 3600)
        
        for filename in os.listdir(self.anomalies_dir):
            if not filename.endswith('.json'):
                continue
            
            filepath = os.path.join(self.anomalies_dir, filename)
            
            if os.path.getmtime(filepath) < cutoff_time:
                continue
            
            with open(filepath, 'r') as f:
                anomalies = json.load(f)
                all_anomalies.extend(anomalies)
        
        logger.info(f"Loaded {len(all_anomalies)} recent anomalies")
        return all_anomalies
    
    def export_to_csv(self, metrics: List[Dict], filename: str):
        """Export metrics to CSV file"""
        df = pd.DataFrame(metrics)
        filepath = os.path.join(self.reports_dir, filename)
        df.to_csv(filepath, index=False)
        logger.info(f"Exported metrics to {filepath}")
        return filepath
    
    def generate_summary_report(self) -> Dict:
        """Generate summary statistics from stored data"""
        all_metrics = self.load_metrics(days=7)
        all_anomalies = self.load_recent_anomalies(hours=168)  # 7 days
        
        if not all_metrics:
            return {
                'error': 'No metrics available',
                'total_metrics': 0,
                'total_anomalies': 0
            }
        
        df = pd.DataFrame(all_metrics)
        
        # Calculate statistics
        summary = {
            'generated_at': datetime.now().isoformat(),
            'period': '7 days',
            'total_metrics': len(all_metrics),
            'total_anomalies': len(all_anomalies),
            'anomaly_rate': len(all_anomalies) / len(all_metrics) if all_metrics else 0,
        }
        
        # Build statistics
        if 'duration' in df.columns:
            summary['avg_duration'] = float(df['duration'].mean())
            summary['max_duration'] = float(df['duration'].max())
        
        if 'result' in df.columns:
            result_counts = df['result'].value_counts().to_dict()
            summary['result_distribution'] = {str(k): int(v) for k, v in result_counts.items()}
            
            # Failure rate
            total = len(df)
            failures = df[df['result'].isin(['FAILURE', 'failure', 'cancelled'])].shape[0]
            summary['failure_rate'] = failures / total if total > 0 else 0
        
        # Job/Workflow statistics
        job_col = 'job_name' if 'job_name' in df.columns else 'workflow_name'
        if job_col in df.columns:
            summary['total_jobs'] = int(df[job_col].nunique())
            summary['builds_per_job'] = len(df) / df[job_col].nunique()
        
        # Save report
        report_file = os.path.join(
            self.reports_dir,
            f"summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        with open(report_file, 'w') as f:
            json.dump(summary, f, indent=2)
        
        logger.info(f"Generated summary report: {report_file}")
        return summary
    
    def cleanup_old_data(self, days: int = 30):
        """Remove data older than specified days"""
        cutoff_time = datetime.now().timestamp() - (days * 86400)
        removed_count = 0
        
        for directory in [self.metrics_dir, self.anomalies_dir, self.reports_dir]:
            for filename in os.listdir(directory):
                filepath = os.path.join(directory, filename)
                
                if os.path.getmtime(filepath) < cutoff_time:
                    os.remove(filepath)
                    removed_count += 1
        
        logger.info(f"Cleaned up {removed_count} old files")
        return removed_count


def main():
    """Example usage"""
    storage = DataStorage('./data')
    
    # Mock metrics
    mock_metrics = [
        {
            'job_name': 'test-job',
            'duration': 120.5,
            'result': 'SUCCESS',
            'timestamp': datetime.now().isoformat(),
        }
        for _ in range(10)
    ]
    
    # Save metrics
    storage.save_metrics(mock_metrics, source='jenkins')
    
    # Load metrics
    loaded = storage.load_metrics(days=7)
    print(f"Loaded {len(loaded)} metrics")
    
    # Generate report
    report = storage.generate_summary_report()
    print("\nSummary Report:")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
