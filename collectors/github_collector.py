"""
GitHub Actions Metrics Collector
Collects workflow run metrics from GitHub Actions
"""

import requests
import json
from datetime import datetime
from typing import Dict, List, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GitHubActionsCollector:
    """Collects pipeline metrics from GitHub Actions"""
    
    def __init__(self, token: str, repo: str):
        self.token = token
        self.repo = repo
        self.base_url = "https://api.github.com"
        self.headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
    def get_workflows(self) -> List[Dict]:
        """Get list of all workflows"""
        try:
            url = f"{self.base_url}/repos/{self.repo}/actions/workflows"
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            return response.json().get('workflows', [])
        except Exception as e:
            logger.error(f"Error fetching workflows: {e}")
            return []
    
    def get_workflow_runs(self, workflow_id: int, per_page: int = 100) -> List[Dict]:
        """Get recent runs for a workflow"""
        try:
            url = f"{self.base_url}/repos/{self.repo}/actions/workflows/{workflow_id}/runs"
            params = {'per_page': per_page, 'status': 'completed'}
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            response.raise_for_status()
            return response.json().get('workflow_runs', [])
        except Exception as e:
            logger.error(f"Error fetching workflow runs for {workflow_id}: {e}")
            return []
    
    def get_run_jobs(self, run_id: int) -> List[Dict]:
        """Get jobs for a specific run"""
        try:
            url = f"{self.base_url}/repos/{self.repo}/actions/runs/{run_id}/jobs"
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            return response.json().get('jobs', [])
        except Exception as e:
            logger.error(f"Error fetching jobs for run {run_id}: {e}")
            return []
    
    def extract_metrics(self, run: Dict, workflow_name: str) -> Dict:
        """Extract relevant metrics from workflow run"""
        created_at = datetime.fromisoformat(run['created_at'].replace('Z', '+00:00'))
        updated_at = datetime.fromisoformat(run['updated_at'].replace('Z', '+00:00'))
        
        if run.get('run_started_at'):
            started_at = datetime.fromisoformat(run['run_started_at'].replace('Z', '+00:00'))
            queue_time = (started_at - created_at).total_seconds()
        else:
            queue_time = 0
        
        duration = (updated_at - created_at).total_seconds()
        
        metrics = {
            'timestamp': created_at.isoformat(),
            'workflow_name': workflow_name,
            'run_number': run.get('run_number', 0),
            'run_id': run.get('id', 0),
            'duration': duration,
            'queue_time': queue_time,
            'result': run.get('conclusion', 'unknown'),
            'event': run.get('event', 'unknown'),
            'attempt': run.get('run_attempt', 1),
        }
        
        return metrics
    
    def get_job_metrics(self, run_id: int) -> Dict:
        """Get detailed job metrics for a run"""
        jobs = self.get_run_jobs(run_id)
        
        metrics = {
            'job_count': len(jobs),
            'step_count': 0,
            'total_job_duration': 0,
            'failed_jobs': 0,
        }
        
        for job in jobs:
            metrics['step_count'] += len(job.get('steps', []))
            
            if job.get('started_at') and job.get('completed_at'):
                started = datetime.fromisoformat(job['started_at'].replace('Z', '+00:00'))
                completed = datetime.fromisoformat(job['completed_at'].replace('Z', '+00:00'))
                metrics['total_job_duration'] += (completed - started).total_seconds()
            
            if job.get('conclusion') == 'failure':
                metrics['failed_jobs'] += 1
        
        return metrics
    
    def collect_all_metrics(self, runs_per_workflow: int = 100, include_jobs: bool = False) -> List[Dict]:
        """Collect metrics from all workflows"""
        workflows = self.get_workflows()
        all_metrics = []
        
        for workflow in workflows:
            workflow_id = workflow['id']
            workflow_name = workflow['name']
            logger.info(f"Collecting metrics for workflow: {workflow_name}")
            
            runs = self.get_workflow_runs(workflow_id, runs_per_workflow)
            
            for run in runs:
                metrics = self.extract_metrics(run, workflow_name)
                
                if include_jobs:
                    job_metrics = self.get_job_metrics(run['id'])
                    metrics.update(job_metrics)
                else:
                    # Set default values
                    metrics.update({
                        'job_count': 0,
                        'step_count': 0,
                        'failed_jobs': 0,
                    })
                
                # Calculate failure metrics
                metrics['failure_count'] = 1 if metrics['result'] in ['failure', 'cancelled'] else 0
                metrics['failure_rate'] = metrics['failure_count']
                
                all_metrics.append(metrics)
        
        logger.info(f"Collected {len(all_metrics)} workflow run metrics")
        return all_metrics


def main():
    """Example usage"""
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    
    token = os.getenv('GITHUB_TOKEN', '')
    repo = os.getenv('GITHUB_REPO', 'owner/repo')
    
    if not token or repo == 'owner/repo':
        logger.warning("GitHub token or repo not configured. Using mock data.")
        print("Please set GITHUB_TOKEN and GITHUB_REPO in .env file")
        return
    
    collector = GitHubActionsCollector(token=token, repo=repo)
    metrics = collector.collect_all_metrics(runs_per_workflow=50)
    
    print(f"Collected {len(metrics)} metrics")
    if metrics:
        print("\nSample metric:")
        print(json.dumps(metrics[0], indent=2))


if __name__ == "__main__":
    main()
