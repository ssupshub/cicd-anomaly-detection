"""
Prometheus Metrics Exporter
Exposes CI/CD metrics and anomaly detection results to Prometheus
"""

from prometheus_client import start_http_server, Gauge, Counter, Histogram, Info
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PrometheusExporter:
    """Exports CI/CD and anomaly detection metrics to Prometheus"""
    
    def __init__(self, port: int = 8000):
        self.port = port
        
        # Pipeline metrics
        self.build_duration = Histogram(
            'cicd_build_duration_seconds',
            'Build duration in seconds',
            ['job_name', 'result']
        )
        
        self.build_count = Counter(
            'cicd_build_total',
            'Total number of builds',
            ['job_name', 'result']
        )
        
        self.queue_time = Histogram(
            'cicd_queue_time_seconds',
            'Time spent in queue',
            ['job_name']
        )
        
        self.test_count = Gauge(
            'cicd_test_count',
            'Number of tests run',
            ['job_name']
        )
        
        self.failure_count = Gauge(
            'cicd_failure_count',
            'Number of test failures',
            ['job_name']
        )
        
        # Anomaly detection metrics
        self.anomaly_score = Gauge(
            'cicd_anomaly_score',
            'Anomaly score for the build',
            ['job_name', 'metric_type']
        )
        
        self.anomaly_detected = Counter(
            'cicd_anomaly_total',
            'Total number of anomalies detected',
            ['job_name', 'anomaly_type']
        )
        
        self.model_accuracy = Gauge(
            'cicd_model_accuracy',
            'Current model accuracy score',
            ['model_name']
        )
        
        self.model_last_trained = Gauge(
            'cicd_model_last_trained_timestamp',
            'Timestamp of last model training',
            ['model_name']
        )
        
        # System metrics
        self.active_jobs = Gauge(
            'cicd_active_jobs',
            'Number of currently active jobs'
        )
        
        self.data_points_collected = Counter(
            'cicd_data_points_total',
            'Total data points collected',
            ['source']
        )
        
        # Info metrics
        self.system_info = Info(
            'cicd_anomaly_detector',
            'Information about the anomaly detection system'
        )
        
    def start(self):
        """Start the Prometheus HTTP server"""
        start_http_server(self.port)
        logger.info(f"Prometheus metrics server started on port {self.port}")
        
        # Set system info
        self.system_info.info({
            'version': '1.0.0',
            'model': 'isolation_forest',
        })
    
    def record_build_metrics(self, metrics: dict):
        """Record build metrics"""
        job_name = metrics.get('job_name', metrics.get('workflow_name', 'unknown'))
        result = metrics.get('result', 'unknown')
        
        # Record duration
        if 'duration' in metrics and metrics['duration'] > 0:
            self.build_duration.labels(
                job_name=job_name,
                result=result
            ).observe(metrics['duration'])
        
        # Record build count
        self.build_count.labels(
            job_name=job_name,
            result=result
        ).inc()
        
        # Record queue time
        if 'queue_time' in metrics and metrics['queue_time'] > 0:
            self.queue_time.labels(job_name=job_name).observe(metrics['queue_time'])
        
        # Record test metrics
        if 'test_count' in metrics:
            self.test_count.labels(job_name=job_name).set(metrics['test_count'])
        
        if 'failure_count' in metrics:
            self.failure_count.labels(job_name=job_name).set(metrics['failure_count'])
        
        # Record data collection
        source = 'jenkins' if 'build_number' in metrics else 'github'
        self.data_points_collected.labels(source=source).inc()
    
    def record_anomaly(self, job_name: str, anomaly_type: str, score: float):
        """Record detected anomaly"""
        self.anomaly_detected.labels(
            job_name=job_name,
            anomaly_type=anomaly_type
        ).inc()
        
        self.anomaly_score.labels(
            job_name=job_name,
            metric_type=anomaly_type
        ).set(score)
    
    def update_model_metrics(self, model_name: str, accuracy: float, timestamp: float):
        """Update model performance metrics"""
        self.model_accuracy.labels(model_name=model_name).set(accuracy)
        self.model_last_trained.labels(model_name=model_name).set(timestamp)
    
    def set_active_jobs(self, count: int):
        """Set number of active jobs"""
        self.active_jobs.set(count)


def main():
    """Example usage"""
    exporter = PrometheusExporter(port=8000)
    exporter.start()
    
    # Simulate some metrics
    import random
    
    jobs = ['build-api', 'test-frontend', 'deploy-prod']
    
    logger.info("Generating sample metrics...")
    
    try:
        while True:
            for job in jobs:
                metrics = {
                    'job_name': job,
                    'duration': random.uniform(60, 600),
                    'queue_time': random.uniform(0, 30),
                    'result': random.choice(['SUCCESS', 'SUCCESS', 'SUCCESS', 'FAILURE']),
                    'test_count': random.randint(50, 200),
                    'failure_count': random.randint(0, 5),
                }
                
                exporter.record_build_metrics(metrics)
                
                # Randomly detect anomalies
                if random.random() < 0.1:
                    exporter.record_anomaly(
                        job_name=job,
                        anomaly_type='duration',
                        score=random.uniform(2.0, 5.0)
                    )
            
            exporter.set_active_jobs(random.randint(0, 5))
            time.sleep(10)
            
    except KeyboardInterrupt:
        logger.info("Shutting down...")


if __name__ == "__main__":
    main()
