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
from collectors.jenkins_collector import JenkinsCollector
from collectors.github_collector import GitHubActionsCollector
from api.alerting import AlertManager
from dotenv import load_dotenv
import logging
from datetime import datetime

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Initialize components
detector = AnomalyDetector()
storage = DataStorage('./data')
alert_manager = AlertManager({
    'slack_webhook_url': os.getenv('SLACK_WEBHOOK_URL', ''),
    'smtp_user': os.getenv('SMTP_USER', ''),
    'smtp_password': os.getenv('SMTP_PASSWORD', ''),
    'alert_email': os.getenv('ALERT_EMAIL', ''),
})

# Try to load existing model
try:
    detector.load_model('./models')
    logger.info("Loaded existing model")
except Exception as e:
    logger.info("No existing model found, will need to train")


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
        
        else:
            return jsonify({'error': 'Invalid source. Use "jenkins" or "github"'}), 400
        
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
    """Train the anomaly detection model"""
    try:
        # Load training data
        days = request.json.get('days', 30) if request.json else 30
        metrics = storage.load_metrics(days=days)
        
        if len(metrics) < 100:
            return jsonify({
                'error': f'Need at least 100 samples, found {len(metrics)}',
                'suggestion': 'Collect more metrics first'
            }), 400
        
        # Train model
        contamination = request.json.get('contamination', 0.1) if request.json else 0.1
        detector.contamination = contamination
        
        stats = detector.train(metrics)
        
        # Save model
        detector.save_model('./models')
        
        return jsonify({
            'success': True,
            'training_stats': stats
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


if __name__ == '__main__':
    port = int(os.getenv('API_PORT', 5000))
    debug = os.getenv('DEBUG', 'true').lower() == 'true'
    
    logger.info(f"Starting API server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=debug)
