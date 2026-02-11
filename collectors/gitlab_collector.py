"""
GitLab CI/CD Metrics Collector
Collects pipeline and job metrics from GitLab
"""

import requests
import json
from datetime import datetime
from typing import Dict, List, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GitLabCollector:
    """Collects CI/CD metrics from GitLab"""
    
    def __init__(self, gitlab_url: str, private_token: str, project_id: str):
        """
        Initialize GitLab collector
        
        Args:
            gitlab_url: GitLab instance URL (e.g., https://gitlab.com)
            private_token: Personal access token
            project_id: Project ID or path (e.g., "group/project")
        """
        self.gitlab_url = gitlab_url.rstrip('/')
        self.project_id = project_id
        self.headers = {
            "PRIVATE-TOKEN": private_token,
            "Content-Type": "application/json"
        }
        self.api_base = f"{self.gitlab_url}/api/v4"
    
    def get_pipelines(self, per_page: int = 100, status: str = None) -> List[Dict]:
        """
        Get list of pipelines
        
        Args:
            per_page: Number of pipelines per page
            status: Filter by status (success, failed, running, etc.)
            
        Returns:
            List of pipeline dictionaries
        """
        try:
            url = f"{self.api_base}/projects/{self.project_id}/pipelines"
            params = {'per_page': per_page}
            
            if status:
                params['status'] = status
            
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            response.raise_for_status()
            
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching pipelines: {e}")
            return []
    
    def get_pipeline_details(self, pipeline_id: int) -> Optional[Dict]:
        """Get detailed information about a specific pipeline"""
        try:
            url = f"{self.api_base}/projects/{self.project_id}/pipelines/{pipeline_id}"
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching pipeline {pipeline_id}: {e}")
            return None
    
    def get_pipeline_jobs(self, pipeline_id: int) -> List[Dict]:
        """Get all jobs for a pipeline"""
        try:
            url = f"{self.api_base}/projects/{self.project_id}/pipelines/{pipeline_id}/jobs"
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching jobs for pipeline {pipeline_id}: {e}")
            return []
    
    def get_pipeline_test_report(self, pipeline_id: int) -> Optional[Dict]:
        """Get test report for a pipeline"""
        try:
            url = f"{self.api_base}/projects/{self.project_id}/pipelines/{pipeline_id}/test_report"
            response = requests.get(url, headers=self.headers, timeout=10)
            
            # Test reports may not exist for all pipelines
            if response.status_code == 404:
                return None
            
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.debug(f"No test report for pipeline {pipeline_id}: {e}")
            return None
    
    def extract_metrics(self, pipeline: Dict, jobs: List[Dict] = None, 
                       test_report: Dict = None) -> Dict:
        """
        Extract metrics from pipeline data
        
        Args:
            pipeline: Pipeline data
            jobs: List of jobs for the pipeline
            test_report: Test report data
            
        Returns:
            Extracted metrics dictionary
        """
        # Parse timestamps
        created_at = datetime.fromisoformat(pipeline['created_at'].replace('Z', '+00:00'))
        
        if pipeline.get('finished_at'):
            finished_at = datetime.fromisoformat(pipeline['finished_at'].replace('Z', '+00:00'))
            duration = (finished_at - created_at).total_seconds()
        else:
            duration = 0
        
        # Calculate queue time
        if pipeline.get('started_at'):
            started_at = datetime.fromisoformat(pipeline['started_at'].replace('Z', '+00:00'))
            queue_time = (started_at - created_at).total_seconds()
        else:
            queue_time = 0
        
        metrics = {
            'timestamp': created_at.isoformat(),
            'pipeline_id': pipeline['id'],
            'pipeline_iid': pipeline.get('iid', 0),
            'ref': pipeline.get('ref', 'unknown'),
            'status': pipeline.get('status', 'unknown'),
            'duration': max(0, duration),
            'queue_time': max(0, queue_time),
            'web_url': pipeline.get('web_url', ''),
        }
        
        # Job metrics
        if jobs:
            metrics['job_count'] = len(jobs)
            metrics['failed_jobs'] = len([j for j in jobs if j.get('status') == 'failed'])
            metrics['step_count'] = len(jobs)  # Each job is a step in GitLab
            
            # Calculate total job duration
            total_job_duration = 0
            for job in jobs:
                if job.get('duration'):
                    total_job_duration += job['duration']
            metrics['total_job_duration'] = total_job_duration
        else:
            metrics['job_count'] = 0
            metrics['failed_jobs'] = 0
            metrics['step_count'] = 0
            metrics['total_job_duration'] = 0
        
        # Test metrics
        if test_report:
            total_count = test_report.get('total_count', 0)
            failed_count = test_report.get('failed_count', 0)
            
            metrics['test_count'] = total_count
            metrics['failure_count'] = failed_count
            metrics['failure_rate'] = failed_count / total_count if total_count > 0 else 0
        else:
            metrics['test_count'] = 0
            metrics['failure_count'] = 0
            metrics['failure_rate'] = 0
        
        # Result mapping
        metrics['result'] = self._map_status(pipeline.get('status', 'unknown'))
        
        return metrics
    
    def _map_status(self, status: str) -> str:
        """Map GitLab status to standard result"""
        status_map = {
            'success': 'SUCCESS',
            'failed': 'FAILURE',
            'canceled': 'CANCELLED',
            'skipped': 'SKIPPED',
            'running': 'RUNNING',
            'pending': 'PENDING',
            'manual': 'MANUAL'
        }
        return status_map.get(status.lower(), 'UNKNOWN')
    
    def collect_all_metrics(self, pipeline_count: int = 100, 
                           include_jobs: bool = True,
                           include_tests: bool = True) -> List[Dict]:
        """
        Collect metrics from all recent pipelines
        
        Args:
            pipeline_count: Number of pipelines to collect
            include_jobs: Whether to fetch job details
            include_tests: Whether to fetch test reports
            
        Returns:
            List of metrics dictionaries
        """
        logger.info(f"Collecting metrics from GitLab project: {self.project_id}")
        
        pipelines = self.get_pipelines(per_page=pipeline_count)
        all_metrics = []
        
        for pipeline in pipelines:
            pipeline_id = pipeline['id']
            
            # Get detailed pipeline info
            detailed_pipeline = self.get_pipeline_details(pipeline_id)
            if not detailed_pipeline:
                continue
            
            # Get jobs if requested
            jobs = None
            if include_jobs:
                jobs = self.get_pipeline_jobs(pipeline_id)
            
            # Get test report if requested
            test_report = None
            if include_tests:
                test_report = self.get_pipeline_test_report(pipeline_id)
            
            # Extract metrics
            metrics = self.extract_metrics(detailed_pipeline, jobs, test_report)
            metrics['workflow_name'] = f"gitlab-{self.project_id}"  # Standardize naming
            
            all_metrics.append(metrics)
        
        logger.info(f"Collected {len(all_metrics)} pipeline metrics from GitLab")
        return all_metrics
    
    def get_project_info(self) -> Optional[Dict]:
        """Get information about the project"""
        try:
            url = f"{self.api_base}/projects/{self.project_id}"
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            project = response.json()
            return {
                'id': project['id'],
                'name': project['name'],
                'path': project['path_with_namespace'],
                'web_url': project['web_url'],
                'default_branch': project.get('default_branch', 'main')
            }
        except Exception as e:
            logger.error(f"Error fetching project info: {e}")
            return None
    
    def get_merge_requests_with_pipelines(self, state: str = 'merged', 
                                         per_page: int = 20) -> List[Dict]:
        """Get merge requests and their pipeline metrics"""
        try:
            url = f"{self.api_base}/projects/{self.project_id}/merge_requests"
            params = {'state': state, 'per_page': per_page}
            
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            response.raise_for_status()
            
            merge_requests = response.json()
            mr_metrics = []
            
            for mr in merge_requests:
                if mr.get('head_pipeline'):
                    pipeline_id = mr['head_pipeline']['id']
                    pipeline = self.get_pipeline_details(pipeline_id)
                    jobs = self.get_pipeline_jobs(pipeline_id)
                    
                    if pipeline:
                        metrics = self.extract_metrics(pipeline, jobs)
                        metrics['merge_request_iid'] = mr['iid']
                        metrics['merge_request_title'] = mr['title']
                        metrics['author'] = mr['author']['name']
                        mr_metrics.append(metrics)
            
            return mr_metrics
        except Exception as e:
            logger.error(f"Error fetching merge requests: {e}")
            return []


def main():
    """Example usage"""
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    
    gitlab_url = os.getenv('GITLAB_URL', 'https://gitlab.com')
    gitlab_token = os.getenv('GITLAB_TOKEN', '')
    gitlab_project = os.getenv('GITLAB_PROJECT', '')
    
    if not gitlab_token or not gitlab_project:
        logger.warning("GitLab credentials not configured")
        print("Please set GITLAB_TOKEN and GITLAB_PROJECT in .env file")
        print("\nExample:")
        print("GITLAB_URL=https://gitlab.com")
        print("GITLAB_TOKEN=your_private_token")
        print("GITLAB_PROJECT=group/project-name")
        return
    
    collector = GitLabCollector(gitlab_url, gitlab_token, gitlab_project)
    
    # Get project info
    project_info = collector.get_project_info()
    if project_info:
        print(f"Project: {project_info['name']}")
        print(f"Path: {project_info['path']}")
        print(f"URL: {project_info['web_url']}")
        print()
    
    # Collect metrics
    metrics = collector.collect_all_metrics(pipeline_count=20)
    
    print(f"Collected {len(metrics)} pipeline metrics")
    
    if metrics:
        print("\nSample metric:")
        print(json.dumps(metrics[0], indent=2))
        
        # Statistics
        successful = len([m for m in metrics if m['result'] == 'SUCCESS'])
        failed = len([m for m in metrics if m['result'] == 'FAILURE'])
        avg_duration = sum(m['duration'] for m in metrics) / len(metrics)
        
        print(f"\nStatistics:")
        print(f"  Success rate: {successful/len(metrics)*100:.1f}%")
        print(f"  Failed: {failed}")
        print(f"  Avg duration: {avg_duration:.1f}s")


if __name__ == "__main__":
    main()
