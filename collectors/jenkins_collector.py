"""
Jenkins Pipeline Metrics Collector
Collects build metrics from Jenkins for anomaly detection
"""

import requests
import json
import time
from datetime import datetime
from typing import Dict, List, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class JenkinsCollector:
    """Collects pipeline metrics from Jenkins"""
    
    def __init__(self, jenkins_url: str, username: str, token: str):
        self.jenkins_url = jenkins_url.rstrip('/')
        self.auth = (username, token)
        self.session = requests.Session()
        self.session.auth = self.auth
        
    def get_job_list(self) -> List[str]:
        """Get list of all jobs"""
        try:
            url = f"{self.jenkins_url}/api/json?tree=jobs[name]"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            jobs = response.json().get('jobs', [])
            return [job['name'] for job in jobs]
        except Exception as e:
            logger.error(f"Error fetching job list: {e}")
            return []
    
    def get_build_info(self, job_name: str, build_number: int) -> Optional[Dict]:
        """Get detailed information about a specific build"""
        try:
            url = f"{self.jenkins_url}/job/{job_name}/{build_number}/api/json"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching build {build_number} for job {job_name}: {e}")
            return None
    
    def get_recent_builds(self, job_name: str, count: int = 100) -> List[Dict]:
        """Get recent builds for a job"""
        try:
            url = f"{self.jenkins_url}/job/{job_name}/api/json?tree=builds[number,duration,result,timestamp,actions[*]]{{0,{count}}}"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            builds = response.json().get('builds', [])
            return builds
        except Exception as e:
            logger.error(f"Error fetching recent builds for {job_name}: {e}")
            return []
    
    def extract_metrics(self, build: Dict) -> Dict:
        """Extract relevant metrics from build data"""
        metrics = {
            'timestamp': datetime.fromtimestamp(build.get('timestamp', 0) / 1000).isoformat(),
            'build_number': build.get('number', 0),
            'duration': build.get('duration', 0) / 1000,  # Convert to seconds
            'result': build.get('result', 'UNKNOWN'),
            'queue_time': 0,
            'test_count': 0,
            'failure_count': 0,
            'step_count': 0,
        }
        
        # Extract additional metrics from actions
        actions = build.get('actions', [])
        for action in actions:
            if action and isinstance(action, dict):
                # Test results
                if action.get('_class', '').endswith('TestResultAction'):
                    metrics['test_count'] = action.get('totalCount', 0)
                    metrics['failure_count'] = action.get('failCount', 0)
                
                # Queue time
                if 'queuingDurationMillis' in action:
                    metrics['queue_time'] = action['queuingDurationMillis'] / 1000
        
        # Calculate failure rate
        if metrics['test_count'] > 0:
            metrics['failure_rate'] = metrics['failure_count'] / metrics['test_count']
        else:
            metrics['failure_rate'] = 1.0 if metrics['result'] == 'FAILURE' else 0.0
        
        return metrics
    
    def collect_all_metrics(self, jobs: Optional[List[str]] = None, builds_per_job: int = 100) -> List[Dict]:
        """Collect metrics from all jobs"""
        if jobs is None:
            jobs = self.get_job_list()
        
        all_metrics = []
        
        for job_name in jobs:
            logger.info(f"Collecting metrics for job: {job_name}")
            builds = self.get_recent_builds(job_name, builds_per_job)
            
            for build in builds:
                if build.get('duration', 0) > 0:  # Only completed builds
                    metrics = self.extract_metrics(build)
                    metrics['job_name'] = job_name
                    all_metrics.append(metrics)
        
        logger.info(f"Collected {len(all_metrics)} build metrics")
        return all_metrics


def main():
    """Example usage"""
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    
    collector = JenkinsCollector(
        jenkins_url=os.getenv('JENKINS_URL', 'http://localhost:8080'),
        username=os.getenv('JENKINS_USER', 'admin'),
        token=os.getenv('JENKINS_TOKEN', '')
    )
    
    metrics = collector.collect_all_metrics(builds_per_job=50)
    print(f"Collected {len(metrics)} metrics")
    if metrics:
        print("\nSample metric:")
        print(json.dumps(metrics[0], indent=2))


if __name__ == "__main__":
    main()
