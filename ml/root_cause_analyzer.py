"""
Root Cause Analysis Engine
Analyzes anomalies to determine probable root causes
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from collections import Counter
import logging
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RootCauseAnalyzer:
    """
    Analyzes anomalies to determine root causes
    Provides actionable insights and recommendations
    """
    
    def __init__(self):
        self.historical_incidents = []
        self.correlation_patterns = {}
        self.common_causes = {}
        
    def analyze(self, anomaly: Dict, historical_data: List[Dict], context: Dict = None) -> Dict:
        """
        Perform root cause analysis on an anomaly
        
        Args:
            anomaly: The detected anomaly
            historical_data: Historical build data for comparison
            context: Additional context (commits, env changes, etc.)
            
        Returns:
            Root cause analysis results
        """
        analysis = {
            'timestamp': datetime.now().isoformat(),
            'anomaly_summary': self._summarize_anomaly(anomaly),
            'probable_causes': [],
            'similar_incidents': [],
            'correlations': [],
            'recommendations': []
        }
        
        # Analyze different aspects
        analysis['probable_causes'] = self._identify_causes(anomaly, historical_data, context)
        analysis['similar_incidents'] = self._find_similar_incidents(anomaly)
        analysis['correlations'] = self._analyze_correlations(anomaly, historical_data)
        analysis['recommendations'] = self._generate_recommendations(analysis)
        
        # Store for future reference
        self.historical_incidents.append({
            'anomaly': anomaly,
            'analysis': analysis,
            'timestamp': datetime.now().isoformat()
        })
        
        return analysis
    
    def _summarize_anomaly(self, anomaly: Dict) -> Dict:
        """Create a summary of the anomaly"""
        data = anomaly.get('data', {})
        features = anomaly.get('anomaly_features', [])
        
        summary = {
            'job_name': data.get('job_name') or data.get('workflow_name', 'Unknown'),
            'severity': anomaly.get('severity', 'unknown'),
            'confidence': anomaly.get('confidence', anomaly.get('max_z_score', 0) / 5),
            'affected_metrics': [f['feature'] for f in features] if features else []
        }
        
        return summary
    
    def _identify_causes(self, anomaly: Dict, historical_data: List[Dict], context: Dict = None) -> List[Dict]:
        """
        Identify probable root causes
        
        Returns list of causes with confidence scores
        """
        causes = []
        data = anomaly.get('data', {})
        features = anomaly.get('anomaly_features', [])
        
        # Analyze each anomalous feature
        for feature_data in features:
            feature = feature_data['feature']
            value = feature_data['value']
            expected = feature_data['expected']
            
            # Duration anomalies
            if feature == 'duration':
                causes.extend(self._analyze_duration_cause(value, expected, data, historical_data, context))
            
            # Failure anomalies
            elif 'failure' in feature:
                causes.extend(self._analyze_failure_cause(value, expected, data, historical_data, context))
            
            # Queue time anomalies
            elif feature == 'queue_time':
                causes.extend(self._analyze_queue_cause(value, expected, data, historical_data, context))
            
            # Test count anomalies
            elif feature == 'test_count':
                causes.extend(self._analyze_test_count_cause(value, expected, data, context))
        
        # Remove duplicates and sort by confidence
        unique_causes = self._deduplicate_causes(causes)
        unique_causes.sort(key=lambda x: x['confidence'], reverse=True)
        
        return unique_causes[:5]  # Top 5 causes
    
    def _analyze_duration_cause(self, value: float, expected: float, data: Dict, 
                                 historical_data: List[Dict], context: Dict = None) -> List[Dict]:
        """Analyze causes of build duration anomalies"""
        causes = []
        ratio = value / expected if expected > 0 else 1
        
        # Check if test count also increased
        if data.get('test_count', 0) > expected:
            test_ratio = data['test_count'] / np.mean([d.get('test_count', 100) for d in historical_data])
            if test_ratio > 1.2:
                causes.append({
                    'cause': 'Increased test count',
                    'description': f"Test suite grew by {(test_ratio-1)*100:.0f}%",
                    'confidence': 0.85,
                    'evidence': {
                        'current_tests': data['test_count'],
                        'avg_tests': np.mean([d.get('test_count', 0) for d in historical_data])
                    }
                })
        
        # Check for external dependencies
        if ratio > 2.0:
            causes.append({
                'cause': 'Potential external dependency issue',
                'description': 'Build took more than 2x normal time, may indicate network/dependency problems',
                'confidence': 0.7,
                'evidence': {
                    'duration_ratio': ratio,
                    'possible_issues': ['Network latency', 'Package registry slow', 'Database connection']
                }
            })
        
        # Check time of day pattern
        if context and 'timestamp' in data:
            hour = self._extract_hour(data['timestamp'])
            if 9 <= hour <= 17:
                causes.append({
                    'cause': 'Peak hour resource contention',
                    'description': f'Build ran during peak hours ({hour}:00), resources may be constrained',
                    'confidence': 0.6,
                    'evidence': {
                        'hour': hour,
                        'peak_hours': '9:00-17:00'
                    }
                })
        
        # Check for code changes (if context provided)
        if context and 'commit_changes' in context:
            changes = context['commit_changes']
            if changes.get('files_changed', 0) > 50:
                causes.append({
                    'cause': 'Large code change',
                    'description': f"{changes['files_changed']} files changed, may increase compile/test time",
                    'confidence': 0.75,
                    'evidence': changes
                })
        
        return causes
    
    def _analyze_failure_cause(self, value: float, expected: float, data: Dict,
                                historical_data: List[Dict], context: Dict = None) -> List[Dict]:
        """Analyze causes of test failure anomalies"""
        causes = []
        
        # High failure rate
        if value > expected * 3:
            causes.append({
                'cause': 'Code regression or breaking change',
                'description': f'Failure count is {value/expected:.1f}x higher than normal',
                'confidence': 0.9,
                'evidence': {
                    'current_failures': int(value),
                    'expected_failures': int(expected),
                    'increase_factor': value/expected if expected > 0 else 0
                }
            })
        
        # Check recent commit patterns
        if context and 'recent_commits' in context:
            commits = context['recent_commits']
            if len(commits) > 5:
                causes.append({
                    'cause': 'Multiple recent changes',
                    'description': f'{len(commits)} commits in short period may have introduced bugs',
                    'confidence': 0.65,
                    'evidence': {
                        'commit_count': len(commits),
                        'authors': list(set(c.get('author', 'unknown') for c in commits))
                    }
                })
        
        # Check if failures are in specific areas
        if context and 'failed_tests' in context:
            failed_tests = context['failed_tests']
            # Group by test file/module
            test_modules = [t.split('::')[0] if '::' in t else t.split('.')[0] 
                          for t in failed_tests]
            module_counts = Counter(test_modules)
            
            if module_counts:
                top_module, count = module_counts.most_common(1)[0]
                if count / len(failed_tests) > 0.5:
                    causes.append({
                        'cause': f'Failures concentrated in {top_module}',
                        'description': f'{count}/{len(failed_tests)} failures in same module',
                        'confidence': 0.8,
                        'evidence': {
                            'affected_module': top_module,
                            'failure_concentration': count / len(failed_tests)
                        }
                    })
        
        return causes
    
    def _analyze_queue_cause(self, value: float, expected: float, data: Dict,
                             historical_data: List[Dict], context: Dict = None) -> List[Dict]:
        """Analyze causes of queue time anomalies"""
        causes = []
        
        # Check concurrent builds
        if context and 'concurrent_builds' in context:
            concurrent = context['concurrent_builds']
            if concurrent > 5:
                causes.append({
                    'cause': 'High concurrent build load',
                    'description': f'{concurrent} concurrent builds competing for resources',
                    'confidence': 0.85,
                    'evidence': {
                        'concurrent_builds': concurrent,
                        'recommendation': 'Consider adding more build agents'
                    }
                })
        
        # Check if it's a resource bottleneck
        if value > expected * 5:
            causes.append({
                'cause': 'Severe resource bottleneck',
                'description': 'Queue time extremely high, build agents likely saturated',
                'confidence': 0.9,
                'evidence': {
                    'queue_time': value,
                    'expected': expected,
                    'urgency': 'high'
                }
            })
        
        return causes
    
    def _analyze_test_count_cause(self, value: float, expected: float, data: Dict, 
                                  context: Dict = None) -> List[Dict]:
        """Analyze causes of test count changes"""
        causes = []
        
        if value > expected * 1.2:
            if context and 'commit_changes' in context:
                changes = context['commit_changes']
                test_files = [f for f in changes.get('files', []) if 'test' in f.lower()]
                
                if test_files:
                    causes.append({
                        'cause': 'New tests added',
                        'description': f'{len(test_files)} test files modified/added',
                        'confidence': 0.95,
                        'evidence': {
                            'test_files_changed': test_files[:5],
                            'total_test_files': len(test_files)
                        }
                    })
        
        return causes
    
    def _find_similar_incidents(self, anomaly: Dict, similarity_threshold: float = 0.7) -> List[Dict]:
        """Find similar historical incidents"""
        if not self.historical_incidents:
            return []
        
        similar = []
        current_features = set(f['feature'] for f in anomaly.get('anomaly_features', []))
        
        for incident in self.historical_incidents[-50:]:  # Last 50 incidents
            past_anomaly = incident['anomaly']
            past_features = set(f['feature'] for f in past_anomaly.get('anomaly_features', []))
            
            # Calculate similarity (Jaccard index)
            if current_features and past_features:
                intersection = len(current_features & past_features)
                union = len(current_features | past_features)
                similarity = intersection / union
                
                if similarity >= similarity_threshold:
                    similar.append({
                        'timestamp': incident['timestamp'],
                        'similarity': similarity,
                        'affected_features': list(past_features),
                        'root_causes': incident['analysis'].get('probable_causes', [])[:2],
                        'resolution': incident.get('resolution', 'Unknown')
                    })
        
        similar.sort(key=lambda x: x['similarity'], reverse=True)
        return similar[:3]  # Top 3 similar incidents
    
    def _analyze_correlations(self, anomaly: Dict, historical_data: List[Dict]) -> List[Dict]:
        """Find correlations between different metrics"""
        correlations = []
        
        if not historical_data or len(historical_data) < 10:
            return correlations
        
        df = pd.DataFrame(historical_data)
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        
        # Calculate correlation matrix
        if len(numeric_cols) > 1:
            corr_matrix = df[numeric_cols].corr()
            
            # Find strong correlations related to anomalous features
            anomalous_features = [f['feature'] for f in anomaly.get('anomaly_features', [])]
            
            for feature in anomalous_features:
                if feature in corr_matrix.columns:
                    for other_feature in corr_matrix.columns:
                        if feature != other_feature:
                            corr_value = corr_matrix.loc[feature, other_feature]
                            
                            if abs(corr_value) > 0.7:
                                correlations.append({
                                    'feature1': feature,
                                    'feature2': other_feature,
                                    'correlation': float(corr_value),
                                    'interpretation': self._interpret_correlation(
                                        feature, other_feature, corr_value
                                    )
                                })
        
        return correlations
    
    def _interpret_correlation(self, feature1: str, feature2: str, correlation: float) -> str:
        """Interpret what a correlation means"""
        direction = "increases" if correlation > 0 else "decreases"
        strength = "strongly" if abs(correlation) > 0.8 else "moderately"
        
        return f"When {feature1} increases, {feature2} {strength} {direction}"
    
    def _generate_recommendations(self, analysis: Dict) -> List[Dict]:
        """Generate actionable recommendations based on analysis"""
        recommendations = []
        
        causes = analysis.get('probable_causes', [])
        
        for cause in causes[:3]:  # Top 3 causes
            cause_type = cause['cause']
            
            # Duration-related recommendations
            if 'test count' in cause_type.lower():
                recommendations.append({
                    'action': 'Optimize test suite',
                    'priority': 'medium',
                    'details': 'Consider parallelizing tests or removing redundant tests',
                    'impact': 'Can reduce build time by 20-40%'
                })
            
            elif 'external dependency' in cause_type.lower():
                recommendations.append({
                    'action': 'Implement caching',
                    'priority': 'high',
                    'details': 'Cache dependencies locally or use a mirror/proxy',
                    'impact': 'Can reduce dependency download time by 80%'
                })
            
            elif 'resource contention' in cause_type.lower() or 'concurrent build' in cause_type.lower():
                recommendations.append({
                    'action': 'Scale build infrastructure',
                    'priority': 'high',
                    'details': 'Add more build agents or upgrade existing ones',
                    'impact': 'Immediate reduction in queue times'
                })
            
            # Failure-related recommendations
            elif 'regression' in cause_type.lower() or 'breaking change' in cause_type.lower():
                recommendations.append({
                    'action': 'Review recent commits',
                    'priority': 'critical',
                    'details': 'Identify and revert the problematic commit',
                    'impact': 'Restore build stability'
                })
            
            elif 'flaky' in cause_type.lower():
                recommendations.append({
                    'action': 'Fix flaky tests',
                    'priority': 'medium',
                    'details': 'Isolate and stabilize intermittently failing tests',
                    'impact': 'Improve build reliability'
                })
        
        # Add general recommendations
        if not recommendations:
            recommendations.append({
                'action': 'Monitor trends',
                'priority': 'low',
                'details': 'Continue monitoring for pattern changes',
                'impact': 'Early detection of issues'
            })
        
        return recommendations
    
    def _deduplicate_causes(self, causes: List[Dict]) -> List[Dict]:
        """Remove duplicate causes"""
        seen = set()
        unique = []
        
        for cause in causes:
            key = cause['cause']
            if key not in seen:
                seen.add(key)
                unique.append(cause)
        
        return unique
    
    def _extract_hour(self, timestamp_str: str) -> int:
        """Extract hour from timestamp string"""
        try:
            if 'T' in timestamp_str:
                time_part = timestamp_str.split('T')[1]
                hour = int(time_part.split(':')[0])
                return hour
        except:
            pass
        return 12  # Default to noon
    
    def get_insights_summary(self) -> Dict:
        """Get summary of insights from all analyzed incidents"""
        if not self.historical_incidents:
            return {'message': 'No incidents analyzed yet'}
        
        # Count top causes
        all_causes = []
        for incident in self.historical_incidents:
            causes = incident['analysis'].get('probable_causes', [])
            all_causes.extend([c['cause'] for c in causes])
        
        cause_counts = Counter(all_causes)
        
        return {
            'total_incidents': len(self.historical_incidents),
            'top_causes': cause_counts.most_common(5),
            'recent_incidents': len([i for i in self.historical_incidents 
                                   if self._is_recent(i['timestamp'], hours=24)])
        }
    
    def _is_recent(self, timestamp_str: str, hours: int = 24) -> bool:
        """Check if timestamp is within last N hours"""
        try:
            ts = datetime.fromisoformat(timestamp_str)
            return datetime.now() - ts < timedelta(hours=hours)
        except:
            return False


def main():
    """Example usage"""
    analyzer = RootCauseAnalyzer()
    
    # Mock historical data
    historical_data = [
        {'duration': 300, 'test_count': 100, 'failure_count': 2, 'queue_time': 10}
        for _ in range(50)
    ]
    
    # Mock anomaly
    anomaly = {
        'data': {
            'job_name': 'build-api',
            'duration': 800,
            'test_count': 150,
            'failure_count': 2,
            'timestamp': '2024-02-08T14:30:00'
        },
        'anomaly_features': [
            {
                'feature': 'duration',
                'value': 800,
                'expected': 300,
                'z_score': 4.5
            },
            {
                'feature': 'test_count',
                'value': 150,
                'expected': 100,
                'z_score': 3.2
            }
        ],
        'severity': 'high'
    }
    
    # Mock context
    context = {
        'commit_changes': {
            'files_changed': 12,
            'files': ['src/api/test_routes.py', 'src/api/test_auth.py']
        },
        'concurrent_builds': 3
    }
    
    # Analyze
    analysis = analyzer.analyze(anomaly, historical_data, context)
    
    print("="*60)
    print("ROOT CAUSE ANALYSIS")
    print("="*60)
    print(json.dumps(analysis, indent=2))


if __name__ == "__main__":
    main()
