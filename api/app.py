"""
REST API for CI/CD Anomaly Detection System
Provides endpoints for monitoring, training, and querying anomalies
"""

from flask import Flask, request, jsonify
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ml.anomaly_detector import AnomalyDetector
from ml.data_storage import DataStorage
from ml.ensemble_detector import EnsembleDetector
from ml.lstm_predictor import LSTMPredictor
from ml.root_cause_analyzer import RootCauseAnalyzer
from ml.flaky_test_detector import FlakyTestDetector
from collectors.jenkins_collector import JenkinsCollector
from collectors.github_collector import GitHubActionsCollector
from collectors.gitlab_collector import GitLabCollector
from api.alerting import AlertManager
from api.smart_alerting import SmartAlertManager, AlertRule, MaintenanceWindow, create_smart_alert_manager
from dotenv import load_dotenv
import logging
from datetime import datetime

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Initialize components
# Create ensemble detector with multiple models
ensemble = EnsembleDetector()

# Add base anomaly detector
base_detector = AnomalyDetector()
ensemble.add_detector('isolation_forest', base_detector, weight=1.2)

# Add LSTM predictor
lstm_predictor = LSTMPredictor(sequence_length=10)
ensemble.add_detector('lstm', lstm_predictor, weight=1.0)

# Keep single detector for backward compatibility
detector = base_detector

# Root cause analyzer
rca = RootCauseAnalyzer()

# Flaky test detector
flaky_detector = FlakyTestDetector(
    flaky_threshold=0.1,
    min_executions=10,
    lookback_days=30
)

# Storage and alerts
storage = DataStorage('./data')

# Base alert manager (unchanged - smart layer wraps it)
_base_alert_manager = AlertManager({
    'slack_webhook_url': os.getenv('SLACK_WEBHOOK_URL', ''),
    'smtp_user': os.getenv('SMTP_USER', ''),
    'smtp_password': os.getenv('SMTP_PASSWORD', ''),
    'alert_email': os.getenv('ALERT_EMAIL', ''),
})

# Smart alert manager wraps the base - drop-in compatible
alert_manager = create_smart_alert_manager(_base_alert_manager, {
    'batch_window_seconds': int(os.getenv('ALERT_BATCH_WINDOW', 60)),
    'dedup_window_seconds': int(os.getenv('ALERT_DEDUP_WINDOW', 300)),
    'max_alerts_per_hour': int(os.getenv('ALERT_MAX_PER_HOUR', 20)),
})

# Try to load existing models
try:
    detector.load_model('./models')
    logger.info("Loaded existing isolation forest model")
except Exception as e:
    logger.info("No existing model found, will need to train")

try:
    ensemble.load_ensemble('./models')
    logger.info("Loaded existing ensemble")
except Exception as e:
    logger.info("No existing ensemble found")


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'model_trained': detector.is_trained
    })


@app.route('/api/v1/collect', methods=['POST'])
def collect_metrics():
    """Collect metrics from CI/CD systems"""
    try:
        source = request.json.get('source', 'jenkins')
        count = request.json.get('count', 100)
        
        metrics = []
        
        if source == 'jenkins':
            jenkins_url = os.getenv('JENKINS_URL', 'http://localhost:8080')
            jenkins_user = os.getenv('JENKINS_USER', 'admin')
            jenkins_token = os.getenv('JENKINS_TOKEN', '')
            
            collector = JenkinsCollector(jenkins_url, jenkins_user, jenkins_token)
            metrics = collector.collect_all_metrics(builds_per_job=count)
            
        elif source == 'github':
            github_token = os.getenv('GITHUB_TOKEN', '')
            github_repo = os.getenv('GITHUB_REPO', '')
            
            if not github_token or not github_repo:
                return jsonify({'error': 'GitHub credentials not configured'}), 400
            
            collector = GitHubActionsCollector(github_token, github_repo)
            metrics = collector.collect_all_metrics(runs_per_workflow=count)
        
        elif source == 'gitlab':
            gitlab_url = os.getenv('GITLAB_URL', 'https://gitlab.com')
            gitlab_token = os.getenv('GITLAB_TOKEN', '')
            gitlab_project = os.getenv('GITLAB_PROJECT', '')
            
            if not gitlab_token or not gitlab_project:
                return jsonify({'error': 'GitLab credentials not configured'}), 400
            
            collector = GitLabCollector(gitlab_url, gitlab_token, gitlab_project)
            metrics = collector.collect_all_metrics(pipeline_count=count)
        
        else:
            return jsonify({'error': 'Invalid source. Use "jenkins", "github", or "gitlab"'}), 400
        
        # Save metrics
        filepath = storage.save_metrics(metrics, source)
        
        return jsonify({
            'success': True,
            'metrics_collected': len(metrics),
            'source': source,
            'filepath': filepath
        })
        
    except Exception as e:
        logger.error(f"Error collecting metrics: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/v1/train', methods=['POST'])
def train_model():
    """Train the anomaly detection model (ensemble + individual models)"""
    try:
        # Load training data
        days = request.json.get('days', 30) if request.json else 30
        use_ensemble = request.json.get('use_ensemble', True) if request.json else True
        metrics = storage.load_metrics(days=days)
        
        if len(metrics) < 100:
            return jsonify({
                'error': f'Need at least 100 samples, found {len(metrics)}',
                'suggestion': 'Collect more metrics first'
            }), 400
        
        results = {}
        
        if use_ensemble:
            # Train ensemble (trains all detectors)
            contamination = request.json.get('contamination', 0.1) if request.json else 0.1
            
            # Update contamination for base detector
            base_detector = ensemble.detectors.get('isolation_forest')
            if base_detector:
                base_detector.contamination = contamination
            
            ensemble_stats = ensemble.train(metrics)
            results['ensemble'] = ensemble_stats
            
            # Save ensemble
            ensemble.save_ensemble('./models')
        else:
            # Train single detector (backward compatibility)
            contamination = request.json.get('contamination', 0.1) if request.json else 0.1
            detector.contamination = contamination
            
            stats = detector.train(metrics)
            results['single_model'] = stats
            
            # Save model
            detector.save_model('./models')
        
        return jsonify({
            'success': True,
            'training_stats': results
        })
        
    except Exception as e:
        logger.error(f"Error training model: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/v1/detect', methods=['POST'])
def detect_anomalies():
    """Detect anomalies in provided metrics"""
    try:
        if not detector.is_trained:
            return jsonify({
                'error': 'Model not trained. Train the model first.',
                'endpoint': '/api/v1/train'
            }), 400
        
        metrics = request.json.get('metrics', [])
        
        if not metrics:
            # Use recent metrics
            metrics = storage.load_metrics(days=1)
        
        if not metrics:
            return jsonify({'error': 'No metrics provided or available'}), 400
        
        # ML-based detection
        predictions, scores = detector.predict(metrics)
        
        # Statistical detection
        threshold = request.json.get('threshold', 3.0) if request.json else 3.0
        stat_anomalies = detector.detect_statistical_anomalies(metrics, threshold)
        
        # Prepare results
        ml_anomalies = []
        for i, (pred, score) in enumerate(zip(predictions, scores)):
            if pred == -1:  # Anomaly
                ml_anomalies.append({
                    'index': i,
                    'score': float(score),
                    'data': metrics[i]
                })
        
        # Save anomalies
        all_anomalies = ml_anomalies + stat_anomalies
        if all_anomalies:
            storage.save_anomalies(all_anomalies)
            
            # Send alerts
            send_alerts = request.json.get('send_alerts', True) if request.json else True
            if send_alerts:
                for anomaly in all_anomalies[:5]:  # Alert for top 5
                    alert_manager.send_alert(anomaly, channels=['slack'])
        
        return jsonify({
            'success': True,
            'total_samples': len(metrics),
            'ml_anomalies': len(ml_anomalies),
            'statistical_anomalies': len(stat_anomalies),
            'anomalies': all_anomalies[:10],  # Return top 10
            'anomaly_rate': len(all_anomalies) / len(metrics) if metrics else 0
        })
        
    except Exception as e:
        logger.error(f"Error detecting anomalies: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/v1/anomalies', methods=['GET'])
def get_anomalies():
    """Get recent anomalies"""
    try:
        hours = request.args.get('hours', default=24, type=int)
        anomalies = storage.load_recent_anomalies(hours=hours)
        
        return jsonify({
            'success': True,
            'count': len(anomalies),
            'period_hours': hours,
            'anomalies': anomalies
        })
        
    except Exception as e:
        logger.error(f"Error retrieving anomalies: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/v1/report', methods=['GET'])
def get_report():
    """Get summary report"""
    try:
        report = storage.generate_summary_report()
        return jsonify(report)
        
    except Exception as e:
        logger.error(f"Error generating report: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/v1/status', methods=['GET'])
def get_status():
    """Get system status"""
    try:
        metrics = storage.load_metrics(days=7)
        anomalies = storage.load_recent_anomalies(hours=168)
        
        return jsonify({
            'model_trained': detector.is_trained,
            'features': detector.feature_names if detector.is_trained else [],
            'total_metrics': len(metrics),
            'total_anomalies': len(anomalies),
            'anomaly_rate': len(anomalies) / len(metrics) if metrics else 0,
            'last_updated': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error getting status: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/v1/pipeline', methods=['POST'])
def run_full_pipeline():
    """Run the complete pipeline: collect, train, detect"""
    try:
        source = request.json.get('source', 'jenkins') if request.json else 'jenkins'
        
        # Step 1: Collect metrics
        logger.info("Step 1: Collecting metrics...")
        if source == 'jenkins':
            jenkins_url = os.getenv('JENKINS_URL', 'http://localhost:8080')
            jenkins_user = os.getenv('JENKINS_USER', 'admin')
            jenkins_token = os.getenv('JENKINS_TOKEN', '')
            
            collector = JenkinsCollector(jenkins_url, jenkins_user, jenkins_token)
            metrics = collector.collect_all_metrics(builds_per_job=200)
        else:
            github_token = os.getenv('GITHUB_TOKEN', '')
            github_repo = os.getenv('GITHUB_REPO', '')
            
            collector = GitHubActionsCollector(github_token, github_repo)
            metrics = collector.collect_all_metrics(runs_per_workflow=200)
        
        storage.save_metrics(metrics, source)
        
        # Step 2: Train model
        logger.info("Step 2: Training model...")
        all_metrics = storage.load_metrics(days=30)
        
        if len(all_metrics) >= 100:
            stats = detector.train(all_metrics)
            detector.save_model('./models')
        else:
            stats = {'error': 'Not enough data to train'}
        
        # Step 3: Detect anomalies
        logger.info("Step 3: Detecting anomalies...")
        if detector.is_trained:
            predictions, scores = detector.predict(metrics)
            stat_anomalies = detector.detect_statistical_anomalies(metrics, threshold=2.5)
            
            ml_anomalies = []
            for i, (pred, score) in enumerate(zip(predictions, scores)):
                if pred == -1:
                    ml_anomalies.append({
                        'index': i,
                        'score': float(score),
                        'data': metrics[i]
                    })
            
            all_anomalies = ml_anomalies + stat_anomalies
            if all_anomalies:
                storage.save_anomalies(all_anomalies)
        else:
            all_anomalies = []
        
        return jsonify({
            'success': True,
            'metrics_collected': len(metrics),
            'training_stats': stats,
            'anomalies_detected': len(all_anomalies)
        })
        
    except Exception as e:
        logger.error(f"Error running pipeline: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/v1/ensemble-detect', methods=['POST'])
def ensemble_detect():
    """Detect anomalies using ensemble method"""
    try:
        if not ensemble.is_trained:
            return jsonify({
                'error': 'Ensemble not trained. Train the model first.',
                'endpoint': '/api/v1/train'
            }), 400
        
        metrics = request.json.get('metrics', [])
        
        if not metrics:
            # Use recent metrics
            metrics = storage.load_metrics(days=1)
        
        if not metrics:
            return jsonify({'error': 'No metrics provided or available'}), 400
        
        # Ensemble detection
        anomalies, voting_stats = ensemble.predict(metrics)
        
        # Save anomalies
        if anomalies:
            storage.save_anomalies(anomalies, 'ensemble')
            
            # Send alerts for high confidence anomalies
            send_alerts = request.json.get('send_alerts', True) if request.json else True
            if send_alerts:
                for anomaly in anomalies[:5]:  # Top 5
                    if anomaly.get('confidence', 0) > 0.7:
                        alert_manager.send_alert(anomaly, channels=['slack'])
        
        return jsonify({
            'success': True,
            'total_samples': len(metrics),
            'anomalies_detected': len(anomalies),
            'voting_stats': voting_stats,
            'anomalies': anomalies[:10]  # Return top 10
        })
        
    except Exception as e:
        logger.error(f"Error in ensemble detection: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/v1/predict', methods=['POST'])
def predict_next_build():
    """Predict metrics for next build using LSTM"""
    try:
        job_name = request.json.get('job_name') if request.json else None
        sequence_length = request.json.get('sequence_length', 20) if request.json else 20
        
        # Get recent builds
        all_metrics = storage.load_metrics(days=7)
        
        if not all_metrics:
            return jsonify({'error': 'No historical data available'}), 400
        
        # Filter by job if specified
        if job_name:
            recent_builds = [m for m in all_metrics if m.get('job_name') == job_name or m.get('workflow_name') == job_name]
        else:
            recent_builds = all_metrics
        
        if len(recent_builds) < sequence_length:
            return jsonify({
                'error': f'Need at least {sequence_length} builds, found {len(recent_builds)}'
            }), 400
        
        # Get LSTM predictor from ensemble
        lstm = ensemble.detectors.get('lstm')
        if not lstm or not lstm.is_trained:
            return jsonify({
                'error': 'LSTM predictor not trained',
                'suggestion': 'Train the ensemble first'
            }), 400
        
        # Make prediction
        predictions = lstm.predict_next(recent_builds[-sequence_length:], job_name)
        
        return jsonify({
            'success': True,
            'job_name': job_name or 'all',
            'predictions': predictions,
            'based_on_builds': len(recent_builds)
        })
        
    except Exception as e:
        logger.error(f"Error in prediction: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/v1/analyze-cause', methods=['POST'])
def analyze_root_cause():
    """Analyze root cause of an anomaly"""
    try:
        anomaly = request.json.get('anomaly')
        context = request.json.get('context', {})
        
        if not anomaly:
            return jsonify({'error': 'Anomaly data required'}), 400
        
        # Get historical data for comparison
        historical_data = storage.load_metrics(days=30)
        
        if not historical_data:
            return jsonify({'error': 'No historical data for analysis'}), 400
        
        # Perform root cause analysis
        analysis = rca.analyze(anomaly, historical_data, context)
        
        return jsonify({
            'success': True,
            'analysis': analysis
        })
        
    except Exception as e:
        logger.error(f"Error in root cause analysis: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/v1/insights', methods=['GET'])
def get_insights():
    """Get insights summary from root cause analyzer"""
    try:
        insights = rca.get_insights_summary()
        return jsonify({
            'success': True,
            'insights': insights
        })
    except Exception as e:
        logger.error(f"Error getting insights: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/v1/flaky-tests/analyze', methods=['POST'])
def analyze_flaky_tests():
    """Analyze test history to detect flaky tests"""
    try:
        # Get test results from recent builds
        days = request.json.get('days', 30) if request.json else 30
        metrics = storage.load_metrics(days=days)
        
        if not metrics:
            return jsonify({'error': 'No metrics available for analysis'}), 400
        
        # Feed test results to detector
        for build in metrics:
            if 'test_results' in build or 'test_count' in build:
                # If test_results not explicitly provided, create from metrics
                if 'test_results' not in build and build.get('test_count', 0) > 0:
                    # Infer test results from failure data
                    build['test_results'] = [{
                        'name': f"test_{i}",
                        'status': 'failed' if i < build.get('failure_count', 0) else 'passed',
                        'duration': 1
                    } for i in range(build.get('test_count', 0))]
                
                flaky_detector.record_test_results(build)
        
        # Analyze for flaky tests
        flaky_tests = flaky_detector.analyze_flaky_tests()
        summary = flaky_detector.get_summary_report()
        
        # Save report
        flaky_detector.save_report('./data/reports/flaky_tests.json')
        
        return jsonify({
            'success': True,
            'flaky_tests_detected': len(flaky_tests),
            'summary': summary,
            'flaky_tests': flaky_tests[:20]  # Return top 20
        })
        
    except Exception as e:
        logger.error(f"Error analyzing flaky tests: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/v1/flaky-tests', methods=['GET'])
def get_flaky_tests():
    """Get list of detected flaky tests"""
    try:
        summary = flaky_detector.get_summary_report()
        
        return jsonify({
            'success': True,
            'summary': summary
        })
        
    except Exception as e:
        logger.error(f"Error getting flaky tests: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/v1/flaky-tests/<test_name>', methods=['GET'])
def get_flaky_test_detail(test_name):
    """Get detailed report for a specific flaky test"""
    try:
        report = flaky_detector.get_flaky_test_report(test_name)
        
        if not report:
            return jsonify({'error': f'Test {test_name} not found or not flaky'}), 404
        
        return jsonify({
            'success': True,
            'test': report
        })
        
    except Exception as e:
        logger.error(f"Error getting flaky test detail: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/v1/alerts/rules', methods=['GET'])
def get_alert_rules():
    """Get all configured alert routing rules"""
    try:
        return jsonify({'success': True, 'rules': alert_manager.list_rules()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/v1/alerts/rules', methods=['POST'])
def add_alert_rule():
    """Add an alert routing rule"""
    try:
        data = request.json or {}
        rule = AlertRule(
            name=data['name'],
            job_pattern=data.get('job_pattern'),
            min_severity=data.get('min_severity', 'medium'),
            channels=data.get('channels', ['slack']),
            team_name=data.get('team_name'),
            slack_webhook=data.get('slack_webhook')
        )
        alert_manager.add_rule(rule)
        return jsonify({'success': True, 'rule': data})
    except KeyError as e:
        return jsonify({'error': f'Missing required field: {e}'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/v1/alerts/rules/<name>', methods=['DELETE'])
def remove_alert_rule(name):
    """Remove an alert routing rule by name"""
    try:
        alert_manager.remove_rule(name)
        return jsonify({'success': True, 'removed': name})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/v1/alerts/maintenance', methods=['GET'])
def get_maintenance_windows():
    """Get active maintenance windows"""
    try:
        return jsonify({
            'success': True,
            'active_windows': alert_manager.list_active_windows()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/v1/alerts/maintenance', methods=['POST'])
def add_maintenance_window():
    """Add a maintenance window to suppress alerts"""
    try:
        data = request.json or {}
        window = MaintenanceWindow(
            name=data['name'],
            start=datetime.fromisoformat(data['start']),
            end=datetime.fromisoformat(data['end']),
            affected_jobs=data.get('affected_jobs')  # None = all jobs
        )
        alert_manager.add_maintenance_window(window)
        return jsonify({'success': True, 'window': data})
    except KeyError as e:
        return jsonify({'error': f'Missing required field: {e}'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/v1/alerts/maintenance/<name>', methods=['DELETE'])
def remove_maintenance_window(name):
    """Remove a maintenance window"""
    try:
        alert_manager.remove_maintenance_window(name)
        return jsonify({'success': True, 'removed': name})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/v1/alerts/stats', methods=['GET'])
def get_alert_stats():
    """Get smart alerting statistics"""
    try:
        return jsonify({'success': True, 'stats': alert_manager.get_stats()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/v1/alerts/flush', methods=['POST'])
def flush_alert_batch():
    """Immediately flush any pending batched alerts"""
    try:
        ok = alert_manager.flush_now()
        return jsonify({'success': ok})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    port = int(os.getenv('API_PORT', 5000))
    debug = os.getenv('DEBUG', 'true').lower() == 'true'
    
    logger.info(f"Starting API server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=debug)
