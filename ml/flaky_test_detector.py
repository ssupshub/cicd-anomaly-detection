"""
Flaky Test Detector
Identifies tests that fail intermittently by tracking test execution history
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import logging
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FlakyTestDetector:
    """
    Detects flaky tests by analyzing test execution history
    A flaky test is one that sometimes passes and sometimes fails without code changes
    """
    
    def __init__(self, 
                 flaky_threshold: float = 0.1,
                 min_executions: int = 10,
                 lookback_days: int = 30):
        """
        Initialize flaky test detector
        
        Args:
            flaky_threshold: Failure rate threshold (0.1 = 10% failure rate)
            min_executions: Minimum number of executions to consider
            lookback_days: Days of history to analyze
        """
        self.flaky_threshold = flaky_threshold
        self.min_executions = min_executions
        self.lookback_days = lookback_days
        
        # Test execution history: {test_name: [results]}
        self.test_history = defaultdict(list)
        
        # Detected flaky tests
        self.flaky_tests = {}
        
        # Statistics
        self.stats = {
            'total_tests_tracked': 0,
            'total_executions': 0,
            'flaky_tests_detected': 0,
            'last_analysis': None
        }
    
    def record_test_results(self, build_data: Dict):
        """
        Record test results from a build
        
        Args:
            build_data: Build data containing test results
        """
        if 'test_results' not in build_data:
            return
        
        build_time = build_data.get('timestamp', datetime.now().isoformat())
        build_id = build_data.get('build_number') or build_data.get('run_number', 0)
        
        for test_result in build_data['test_results']:
            test_name = test_result.get('name')
            status = test_result.get('status', 'unknown')
            duration = test_result.get('duration', 0)
            
            if not test_name:
                continue
            
            self.test_history[test_name].append({
                'timestamp': build_time,
                'build_id': build_id,
                'status': status,
                'duration': duration,
                'passed': status in ['passed', 'success', 'SUCCESS'],
                'failed': status in ['failed', 'failure', 'FAILURE', 'error']
            })
            
            self.stats['total_executions'] += 1
        
        self.stats['total_tests_tracked'] = len(self.test_history)
    
    def analyze_flaky_tests(self) -> List[Dict]:
        """
        Analyze test history to detect flaky tests
        
        Returns:
            List of flaky test reports
        """
        logger.info(f"Analyzing {len(self.test_history)} tests for flakiness...")
        
        flaky_tests = []
        cutoff_date = datetime.now() - timedelta(days=self.lookback_days)
        
        for test_name, executions in self.test_history.items():
            # Filter to recent executions
            recent_executions = [
                e for e in executions
                if self._parse_timestamp(e['timestamp']) >= cutoff_date
            ]
            
            if len(recent_executions) < self.min_executions:
                continue
            
            # Calculate statistics
            total_runs = len(recent_executions)
            failures = sum(1 for e in recent_executions if e['failed'])
            passes = sum(1 for e in recent_executions if e['passed'])
            
            if total_runs == 0:
                continue
            
            failure_rate = failures / total_runs
            
            # A test is flaky if it both passes AND fails (not always failing)
            has_passes = passes > 0
            has_failures = failures > 0
            is_intermittent = has_passes and has_failures
            
            # Check if it meets flaky criteria
            if is_intermittent and failure_rate >= self.flaky_threshold:
                flaky_info = self._analyze_flaky_pattern(test_name, recent_executions)
                flaky_info.update({
                    'test_name': test_name,
                    'total_runs': total_runs,
                    'failures': failures,
                    'passes': passes,
                    'failure_rate': failure_rate,
                    'flakiness_score': self._calculate_flakiness_score(recent_executions),
                    'severity': self._determine_severity(failure_rate, total_runs)
                })
                
                flaky_tests.append(flaky_info)
        
        # Sort by flakiness score (worst first)
        flaky_tests.sort(key=lambda x: x['flakiness_score'], reverse=True)
        
        self.flaky_tests = {test['test_name']: test for test in flaky_tests}
        self.stats['flaky_tests_detected'] = len(flaky_tests)
        self.stats['last_analysis'] = datetime.now().isoformat()
        
        logger.info(f"Detected {len(flaky_tests)} flaky tests")
        
        return flaky_tests
    
    def _analyze_flaky_pattern(self, test_name: str, executions: List[Dict]) -> Dict:
        """Analyze the pattern of flakiness"""
        # Sort by timestamp
        sorted_exec = sorted(executions, key=lambda x: x['timestamp'])
        
        # Find streaks of passes and failures
        current_streak = None
        streak_lengths = []
        
        for execution in sorted_exec:
            status = 'pass' if execution['passed'] else 'fail'
            
            if status != current_streak:
                if current_streak is not None:
                    streak_lengths.append(len([e for e in sorted_exec if e == current_streak]))
                current_streak = status
        
        # Calculate pattern metrics
        pattern_info = {
            'last_failure': None,
            'last_pass': None,
            'consecutive_failures': 0,
            'max_consecutive_failures': 0,
            'flip_flops': 0  # Number of pass/fail transitions
        }
        
        # Find last failure and pass
        for execution in reversed(sorted_exec):
            if execution['failed'] and not pattern_info['last_failure']:
                pattern_info['last_failure'] = execution['timestamp']
            if execution['passed'] and not pattern_info['last_pass']:
                pattern_info['last_pass'] = execution['timestamp']
            if pattern_info['last_failure'] and pattern_info['last_pass']:
                break
        
        # Count consecutive failures from most recent
        for execution in reversed(sorted_exec):
            if execution['failed']:
                pattern_info['consecutive_failures'] += 1
            else:
                break
        
        # Count flip-flops (status changes)
        for i in range(1, len(sorted_exec)):
            if sorted_exec[i]['passed'] != sorted_exec[i-1]['passed']:
                pattern_info['flip_flops'] += 1
        
        # Find max consecutive failures
        current_consecutive = 0
        max_consecutive = 0
        for execution in sorted_exec:
            if execution['failed']:
                current_consecutive += 1
                max_consecutive = max(max_consecutive, current_consecutive)
            else:
                current_consecutive = 0
        
        pattern_info['max_consecutive_failures'] = max_consecutive
        
        return pattern_info
    
    def _calculate_flakiness_score(self, executions: List[Dict]) -> float:
        """
        Calculate flakiness score (0-100)
        Higher score = more problematic
        """
        if not executions:
            return 0
        
        failures = sum(1 for e in executions if e['failed'])
        total = len(executions)
        failure_rate = failures / total
        
        # Count transitions between pass/fail
        transitions = 0
        for i in range(1, len(executions)):
            if executions[i]['passed'] != executions[i-1]['passed']:
                transitions += 1
        
        transition_rate = transitions / max(total - 1, 1)
        
        # Flakiness score combines:
        # - Failure rate (40%)
        # - Transition rate (40%) - high transitions = more flaky
        # - Recency (20%) - recent failures weighted more
        
        recency_weight = 0
        for i, execution in enumerate(reversed(executions[:10])):  # Last 10 runs
            if execution['failed']:
                recency_weight += (10 - i) / 10
        recency_weight /= min(10, total)
        
        score = (failure_rate * 40) + (transition_rate * 40) + (recency_weight * 20)
        
        return min(100, score * 100)  # Scale to 0-100
    
    def _determine_severity(self, failure_rate: float, total_runs: int) -> str:
        """Determine severity level of flaky test"""
        if failure_rate > 0.5:
            return 'critical'  # Fails more than half the time
        elif failure_rate > 0.3:
            return 'high'
        elif failure_rate > 0.15:
            return 'medium'
        else:
            return 'low'
    
    def _parse_timestamp(self, timestamp_str: str) -> datetime:
        """Parse timestamp string to datetime"""
        try:
            if 'T' in timestamp_str:
                return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            return datetime.fromisoformat(timestamp_str)
        except:
            return datetime.now()
    
    def get_flaky_test_report(self, test_name: str) -> Optional[Dict]:
        """Get detailed report for a specific flaky test"""
        if test_name not in self.flaky_tests:
            return None
        
        test_info = self.flaky_tests[test_name].copy()
        
        # Add recent execution history
        recent_history = self.test_history[test_name][-20:]  # Last 20 runs
        test_info['recent_history'] = [
            {
                'timestamp': e['timestamp'],
                'status': 'passed' if e['passed'] else 'failed',
                'build_id': e['build_id']
            }
            for e in recent_history
        ]
        
        # Add recommendations
        test_info['recommendations'] = self._generate_recommendations(test_info)
        
        return test_info
    
    def _generate_recommendations(self, test_info: Dict) -> List[Dict]:
        """Generate recommendations for fixing flaky test"""
        recommendations = []
        
        failure_rate = test_info['failure_rate']
        flip_flops = test_info.get('flip_flops', 0)
        
        # High flip-flop rate suggests timing issues
        if flip_flops > 5:
            recommendations.append({
                'issue': 'High variability in results',
                'likely_cause': 'Race condition or timing dependency',
                'action': 'Add explicit waits or synchronization',
                'priority': 'high',
                'effort': 'medium'
            })
        
        # Moderate failure rate suggests environmental issues
        if 0.2 <= failure_rate <= 0.4:
            recommendations.append({
                'issue': 'Intermittent failures',
                'likely_cause': 'External dependency or network issue',
                'action': 'Add retries or mock external dependencies',
                'priority': 'medium',
                'effort': 'low'
            })
        
        # High failure rate suggests test needs rewrite
        if failure_rate > 0.5:
            recommendations.append({
                'issue': 'Frequent failures',
                'likely_cause': 'Test design issue or actual bug',
                'action': 'Review and rewrite test, or fix underlying bug',
                'priority': 'critical',
                'effort': 'high'
            })
        
        # Recent consecutive failures
        if test_info.get('consecutive_failures', 0) >= 3:
            recommendations.append({
                'issue': 'Recent consecutive failures',
                'likely_cause': 'Recent code change broke test',
                'action': 'Review recent commits affecting this test',
                'priority': 'high',
                'effort': 'low'
            })
        
        # Default recommendation
        if not recommendations:
            recommendations.append({
                'issue': 'Test occasionally fails',
                'likely_cause': 'Unknown - needs investigation',
                'action': 'Add logging and monitor for patterns',
                'priority': 'low',
                'effort': 'low'
            })
        
        return recommendations
    
    def get_summary_report(self) -> Dict:
        """Get summary of all flaky tests"""
        if not self.flaky_tests:
            return {
                'total_flaky_tests': 0,
                'message': 'No flaky tests detected'
            }
        
        severity_counts = Counter(test['severity'] for test in self.flaky_tests.values())
        
        # Calculate impact
        total_wasted_time = 0
        avg_test_duration = 30  # seconds, assumption
        
        for test in self.flaky_tests.values():
            failures = test['failures']
            total_wasted_time += failures * avg_test_duration
        
        return {
            'total_flaky_tests': len(self.flaky_tests),
            'by_severity': dict(severity_counts),
            'top_offenders': list(self.flaky_tests.values())[:10],
            'estimated_wasted_time_seconds': total_wasted_time,
            'estimated_wasted_time_hours': round(total_wasted_time / 3600, 2),
            'stats': self.stats
        }
    
    def save_report(self, filepath: str):
        """Save flaky test report to file"""
        report = {
            'generated_at': datetime.now().isoformat(),
            'summary': self.get_summary_report(),
            'flaky_tests': list(self.flaky_tests.values()),
            'stats': self.stats
        }
        
        with open(filepath, 'w') as f:
            json.dump(report, f, indent=2)
        
        logger.info(f"Flaky test report saved to {filepath}")
    
    def load_history(self, filepath: str):
        """Load test history from file"""
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        self.test_history = defaultdict(list, data.get('test_history', {}))
        self.stats = data.get('stats', self.stats)
        
        logger.info(f"Loaded history for {len(self.test_history)} tests")


def main():
    """Example usage"""
    detector = FlakyTestDetector(
        flaky_threshold=0.1,
        min_executions=10
    )
    
    # Simulate test results from multiple builds
    np.random.seed(42)
    
    test_names = [
        'test_login',
        'test_user_registration',
        'test_api_endpoint',
        'test_database_connection',  # This will be flaky
        'test_payment_processing',   # This will be flaky
        'test_email_sending'
    ]
    
    print("Simulating 50 builds with test results...")
    
    for build_num in range(1, 51):
        build_data = {
            'build_number': build_num,
            'timestamp': (datetime.now() - timedelta(days=50-build_num)).isoformat(),
            'test_results': []
        }
        
        for test_name in test_names:
            # Simulate flaky tests
            if 'database' in test_name:
                # Flaky: fails 15% of the time randomly
                status = 'failed' if np.random.random() < 0.15 else 'passed'
            elif 'payment' in test_name:
                # Very flaky: fails 40% of the time
                status = 'failed' if np.random.random() < 0.40 else 'passed'
            else:
                # Stable: fails rarely
                status = 'failed' if np.random.random() < 0.02 else 'passed'
            
            build_data['test_results'].append({
                'name': test_name,
                'status': status,
                'duration': np.random.uniform(1, 60)
            })
        
        detector.record_test_results(build_data)
    
    # Analyze for flaky tests
    print("\nAnalyzing test history...\n")
    flaky_tests = detector.analyze_flaky_tests()
    
    # Display results
    print("=" * 60)
    print("FLAKY TEST DETECTION REPORT")
    print("=" * 60)
    
    summary = detector.get_summary_report()
    print(f"\nSummary:")
    print(f"  Total tests tracked: {summary['stats']['total_tests_tracked']}")
    print(f"  Total executions: {summary['stats']['total_executions']}")
    print(f"  Flaky tests detected: {summary['total_flaky_tests']}")
    print(f"  Estimated wasted time: {summary['estimated_wasted_time_hours']} hours")
    
    if summary['by_severity']:
        print(f"\n  By severity:")
        for severity, count in summary['by_severity'].items():
            print(f"    {severity}: {count}")
    
    print("\n" + "=" * 60)
    print("FLAKY TESTS DETAILS")
    print("=" * 60)
    
    for i, test in enumerate(flaky_tests, 1):
        print(f"\n{i}. {test['test_name']}")
        print(f"   Flakiness Score: {test['flakiness_score']:.1f}/100")
        print(f"   Severity: {test['severity'].upper()}")
        print(f"   Failure Rate: {test['failure_rate']:.1%} ({test['failures']}/{test['total_runs']})")
        print(f"   Flip-flops: {test['flip_flops']}")
        print(f"   Consecutive failures: {test['consecutive_failures']}")
        
        # Get detailed report
        report = detector.get_flaky_test_report(test['test_name'])
        if report['recommendations']:
            print(f"\n   Recommendations:")
            for rec in report['recommendations'][:2]:  # Top 2
                print(f"   [{rec['priority'].upper()}] {rec['action']}")
                print(f"      Likely cause: {rec['likely_cause']}")
    
    # Save report
    detector.save_report('./flaky_test_report.json')
    print("\n\nFull report saved to: ./flaky_test_report.json")


if __name__ == "__main__":
    main()
