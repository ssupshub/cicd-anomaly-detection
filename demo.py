#!/usr/bin/env python
"""
Quick Start Demo
Demonstrates the CI/CD anomaly detection system with mock data
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import time
from ml.anomaly_detector import AnomalyDetector
from ml.data_storage import DataStorage
from api.alerting import AlertManager
import json


def generate_mock_pipeline_data(n_samples=200):
    """Generate realistic mock CI/CD pipeline data"""
    print("📊 Generating mock pipeline data...")
    
    jobs = ['build-api', 'test-frontend', 'deploy-staging', 'integration-tests', 'deploy-prod']
    data = []
    
    # Normal builds
    for i in range(n_samples):
        job = np.random.choice(jobs)
        
        # Different jobs have different characteristics
        if 'test' in job:
            base_duration = 180
            base_tests = 150
        elif 'deploy' in job:
            base_duration = 120
            base_tests = 50
        else:
            base_duration = 240
            base_tests = 100
        
        data.append({
            'job_name': job,
            'build_number': i + 1,
            'duration': np.random.normal(base_duration, 30),
            'queue_time': np.random.exponential(5),
            'test_count': int(np.random.normal(base_tests, 10)),
            'failure_count': np.random.poisson(1),
            'step_count': np.random.randint(5, 12),
            'result': np.random.choice(['SUCCESS', 'SUCCESS', 'SUCCESS', 'FAILURE'], p=[0.85, 0.1, 0.04, 0.01]),
            'timestamp': f"2024-02-{(i % 28) + 1:02d}T{(i % 24):02d}:00:00"
        })
        
        # Calculate derived metrics
        data[-1]['failure_rate'] = data[-1]['failure_count'] / max(data[-1]['test_count'], 1)
        data[-1]['job_count'] = 1
        data[-1]['failed_jobs'] = 1 if data[-1]['result'] == 'FAILURE' else 0
    
    # Add some anomalies
    print("🚨 Adding anomalous builds...")
    anomaly_indices = np.random.choice(range(len(data)), size=15, replace=False)
    
    for idx in anomaly_indices:
        anomaly_type = np.random.choice(['slow', 'failures', 'queue'])
        
        if anomaly_type == 'slow':
            data[idx]['duration'] = np.random.normal(600, 100)
        elif anomaly_type == 'failures':
            data[idx]['failure_count'] = np.random.randint(15, 30)
            data[idx]['failure_rate'] = data[idx]['failure_count'] / max(data[idx]['test_count'], 1)
            data[idx]['result'] = 'FAILURE'
        else:  # queue
            data[idx]['queue_time'] = np.random.uniform(60, 120)
    
    print(f"✅ Generated {len(data)} builds ({len(anomaly_indices)} anomalous)")
    return data


def main():
    """Run the demo"""
    print("=" * 60)
    print("🤖 CI/CD Anomaly Detection System - Quick Start Demo")
    print("=" * 60)
    print()
    
    # Initialize components
    print("🔧 Initializing components...")
    detector = AnomalyDetector(contamination=0.1)
    storage = DataStorage('./data')
    
    # Generate mock data
    pipeline_data = generate_mock_pipeline_data(200)
    
    # Save data
    print("\n💾 Saving data...")
    storage.save_metrics(pipeline_data, 'demo')
    
    # Train model
    print("\n🧠 Training anomaly detection model...")
    print("   Using Isolation Forest algorithm...")
    
    stats = detector.train(pipeline_data)
    
    print(f"\n📈 Training Results:")
    print(f"   • Samples: {stats['samples']}")
    print(f"   • Features: {stats['features']}")
    print(f"   • Anomalies detected in training: {stats['anomalies_detected']}")
    print(f"   • Anomaly rate: {stats['anomaly_rate']:.1%}")
    
    # Save model
    detector.save_model('./models')
    print("\n✅ Model saved to ./models/")
    
    # Test on new data
    print("\n🔍 Testing on new builds...")
    test_data = generate_mock_pipeline_data(50)
    
    # ML-based detection
    predictions, scores = detector.predict(test_data)
    ml_anomalies = sum(1 for p in predictions if p == -1)
    
    # Statistical detection
    stat_anomalies = detector.detect_statistical_anomalies(test_data, threshold=2.5)
    
    print(f"\n🎯 Detection Results:")
    print(f"   • Test samples: {len(test_data)}")
    print(f"   • ML anomalies: {ml_anomalies}")
    print(f"   • Statistical anomalies: {len(stat_anomalies)}")
    
    # Show example anomalies
    if stat_anomalies:
        print("\n🚨 Example Anomaly Details:")
        anomaly = stat_anomalies[0]
        print(f"   Job: {anomaly['data'].get('job_name', 'Unknown')}")
        print(f"   Max Z-Score: {anomaly['max_z_score']:.2f}")
        print(f"   Anomalous features:")
        
        for feature in anomaly['anomaly_features'][:3]:
            print(f"      • {feature['feature']}: {feature['value']:.1f} ")
            print(f"        (expected: {feature['expected']:.1f}, z-score: {feature['z_score']:.2f})")
    
    # Save anomalies
    all_anomalies = stat_anomalies
    if all_anomalies:
        storage.save_anomalies(all_anomalies, 'demo')
        print(f"\n💾 Saved {len(all_anomalies)} anomalies")
    
    # Generate report
    print("\n📊 Generating summary report...")
    report = storage.generate_summary_report()
    
    print(f"\n📋 Summary Report:")
    print(f"   • Total metrics: {report.get('total_metrics', 0)}")
    print(f"   • Total anomalies: {report.get('total_anomalies', 0)}")
    print(f"   • Anomaly rate: {report.get('anomaly_rate', 0):.1%}")
    
    if 'avg_duration' in report:
        print(f"   • Average build duration: {report['avg_duration']:.1f}s")
    
    if 'failure_rate' in report:
        print(f"   • Overall failure rate: {report['failure_rate']:.1%}")
    
    # Test alert formatting
    print("\n📧 Alert Preview:")
    if all_anomalies:
        alert_mgr = AlertManager()
        message = alert_mgr.format_anomaly_message(all_anomalies[0])
        print("\n" + "-" * 60)
        print(message)
        print("-" * 60)
    
    # Summary
    print("\n" + "=" * 60)
    print("✅ Demo Complete!")
    print("=" * 60)
    print("\n📁 Files created:")
    print("   • ./data/metrics/      - Collected metrics")
    print("   • ./data/anomalies/    - Detected anomalies")
    print("   • ./data/reports/      - Summary reports")
    print("   • ./models/            - Trained ML model")
    
    print("\n🚀 Next Steps:")
    print("   1. Configure your Jenkins/GitHub credentials in .env")
    print("   2. Start the API: python api/app.py")
    print("   3. Start monitoring: python scheduler.py")
    print("   4. View dashboard: docker-compose up -d")
    print("   5. Access Grafana: http://localhost:3000")
    
    print("\n📚 API Documentation:")
    print("   http://localhost:5000/health")
    print("   http://localhost:5000/api/v1/status")
    print()


if __name__ == "__main__":
    main()
