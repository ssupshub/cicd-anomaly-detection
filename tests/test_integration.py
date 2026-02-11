"""
Integration Test for Phase 1-3 Features
Tests that all new components integrate properly with existing system
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from ml.anomaly_detector import AnomalyDetector
from ml.ensemble_detector import EnsembleDetector
from ml.lstm_predictor import LSTMPredictor
from ml.root_cause_analyzer import RootCauseAnalyzer
from ml.data_storage import DataStorage


def generate_test_data(n=200):
    """Generate test data"""
    data = []
    for i in range(n):
        data.append({
            'job_name': 'test-job',
            'duration': np.random.normal(300, 50),
            'queue_time': np.random.normal(10, 3),
            'test_count': np.random.randint(80, 120),
            'failure_count': np.random.randint(0, 3),
            'failure_rate': np.random.uniform(0, 0.05),
            'step_count': np.random.randint(5, 15),
            'job_count': 1,
            'failed_jobs': 0,
            'timestamp': f"2024-02-{(i % 28) + 1:02d}T{(i % 24):02d}:00:00"
        })
    
    # Add some anomalies
    for i in range(20):
        data.append({
            'job_name': 'test-job',
            'duration': np.random.normal(800, 100),
            'queue_time': np.random.normal(50, 10),
            'test_count': np.random.randint(80, 120),
            'failure_count': np.random.randint(10, 20),
            'failure_rate': np.random.uniform(0.1, 0.3),
            'step_count': np.random.randint(5, 15),
            'job_count': 1,
            'failed_jobs': 1,
            'timestamp': f"2024-02-{(i % 28) + 1:02d}T{(i % 24):02d}:00:00"
        })
    
    np.random.shuffle(data)
    return data


def test_1_base_detector():
    """Test 1: Base Anomaly Detector (original system)"""
    print("\n" + "="*60)
    print("TEST 1: Base Anomaly Detector")
    print("="*60)
    
    try:
        detector = AnomalyDetector()
        data = generate_test_data(200)
        
        # Train
        stats = detector.train(data[:180])
        print(f"✓ Training successful: {stats['samples']} samples")
        
        # Predict
        predictions, scores = detector.predict(data[180:])
        anomaly_count = (predictions == -1).sum()
        print(f"✓ Prediction successful: {anomaly_count} anomalies detected")
        
        # Statistical detection
        stat_anomalies = detector.detect_statistical_anomalies(data[180:])
        print(f"✓ Statistical detection: {len(stat_anomalies)} anomalies")
        
        return True
    except Exception as e:
        print(f"✗ Test failed: {e}")
        return False


def test_2_lstm_predictor():
    """Test 2: LSTM Predictor"""
    print("\n" + "="*60)
    print("TEST 2: LSTM Time Series Predictor")
    print("="*60)
    
    try:
        predictor = LSTMPredictor(sequence_length=10)
        data = generate_test_data(150)
        
        # Train
        stats = predictor.train(data[:130])
        print(f"✓ Training successful (method: {stats['method']})")
        
        # Predict
        recent = data[110:130]
        predictions = predictor.predict_next(recent)
        print(f"✓ Prediction successful: {len(predictions)} metrics predicted")
        
        # Detect anomaly from prediction
        actual = data[130]
        anomalies = predictor.detect_anomaly_from_prediction(actual, predictions)
        print(f"✓ Anomaly detection: {len(anomalies)} prediction-based anomalies")
        
        return True
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_3_ensemble_detector():
    """Test 3: Ensemble Detector"""
    print("\n" + "="*60)
    print("TEST 3: Ensemble Detector")
    print("="*60)
    
    try:
        ensemble = EnsembleDetector()
        
        # Add detectors
        base_detector = AnomalyDetector()
        lstm_predictor = LSTMPredictor(sequence_length=10)
        
        ensemble.add_detector('isolation_forest', base_detector, weight=1.2)
        ensemble.add_detector('lstm', lstm_predictor, weight=1.0)
        print(f"✓ Added {len(ensemble.detectors)} detectors")
        
        # Train
        data = generate_test_data(200)
        train_stats = ensemble.train(data[:180])
        print(f"✓ Training successful: {train_stats['ensemble_size']} detectors")
        
        # Predict
        anomalies, voting_stats = ensemble.predict(data[180:])
        print(f"✓ Ensemble detection: {len(anomalies)} anomalies")
        print(f"  - Reduction rate: {voting_stats['reduction_rate']:.1%}")
        
        return True
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_4_root_cause_analyzer():
    """Test 4: Root Cause Analyzer"""
    print("\n" + "="*60)
    print("TEST 4: Root Cause Analyzer")
    print("="*60)
    
    try:
        rca = RootCauseAnalyzer()
        data = generate_test_data(100)
        
        # Create mock anomaly
        anomaly = {
            'data': {
                'job_name': 'test-job',
                'duration': 800,
                'test_count': 150,
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
            ]
        }
        
        context = {
            'commit_changes': {'files_changed': 12},
            'concurrent_builds': 3
        }
        
        # Analyze
        analysis = rca.analyze(anomaly, data, context)
        print(f"✓ Root cause analysis successful")
        print(f"  - Probable causes: {len(analysis['probable_causes'])}")
        print(f"  - Recommendations: {len(analysis['recommendations'])}")
        
        if analysis['probable_causes']:
            top_cause = analysis['probable_causes'][0]
            print(f"  - Top cause: {top_cause['cause']} ({top_cause['confidence']:.0%})")
        
        return True
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_5_data_storage_compatibility():
    """Test 5: Data Storage Compatibility"""
    print("\n" + "="*60)
    print("TEST 5: Data Storage Compatibility")
    print("="*60)
    
    try:
        storage = DataStorage('./test_data')
        data = generate_test_data(50)
        
        # Save metrics
        filepath = storage.save_metrics(data, 'test')
        print(f"✓ Saved metrics to {filepath}")
        
        # Load metrics
        loaded = storage.load_metrics(days=7)
        print(f"✓ Loaded {len(loaded)} metrics")
        
        # Save anomalies
        anomalies = [{'index': 0, 'score': 0.5, 'data': data[0]}]
        storage.save_anomalies(anomalies, 'test')
        print(f"✓ Saved anomalies")
        
        # Generate report
        report = storage.generate_summary_report()
        print(f"✓ Generated report: {report['total_metrics']} metrics")
        
        # Cleanup
        import shutil
        shutil.rmtree('./test_data')
        
        return True
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_6_end_to_end_integration():
    """Test 6: End-to-End Integration"""
    print("\n" + "="*60)
    print("TEST 6: End-to-End Integration")
    print("="*60)
    
    try:
        # Generate data
        data = generate_test_data(200)
        print("✓ Generated test data")
        
        # Create all components
        ensemble = EnsembleDetector()
        ensemble.add_detector('isolation_forest', AnomalyDetector(), weight=1.2)
        ensemble.add_detector('lstm', LSTMPredictor(), weight=1.0)
        print("✓ Created ensemble")
        
        rca = RootCauseAnalyzer()
        storage = DataStorage('./test_data_e2e')
        print("✓ Created components")
        
        # Save data
        storage.save_metrics(data, 'integration_test')
        print("✓ Saved data")
        
        # Train ensemble
        train_stats = ensemble.train(data[:180])
        print(f"✓ Trained ensemble: {train_stats['successful']} models")
        
        # Detect anomalies
        anomalies, voting_stats = ensemble.predict(data[180:])
        print(f"✓ Detected {len(anomalies)} anomalies")
        
        # Analyze causes
        for anomaly in anomalies[:3]:
            analysis = rca.analyze(anomaly, data[:180])
            print(f"✓ Analyzed anomaly (causes: {len(analysis['probable_causes'])})")
        
        # Save results
        storage.save_anomalies(anomalies, 'ensemble')
        print("✓ Saved results")
        
        # Cleanup
        import shutil
        shutil.rmtree('./test_data_e2e')
        
        return True
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all integration tests"""
    print("="*60)
    print("PHASE 1-3 INTEGRATION TESTS")
    print("="*60)
    print("\nTesting new features with existing system...")
    
    results = []
    
    # Run tests
    results.append(('Base Detector', test_1_base_detector()))
    results.append(('LSTM Predictor', test_2_lstm_predictor()))
    results.append(('Ensemble Detector', test_3_ensemble_detector()))
    results.append(('Root Cause Analyzer', test_4_root_cause_analyzer()))
    results.append(('Data Storage', test_5_data_storage_compatibility()))
    results.append(('End-to-End', test_6_end_to_end_integration()))
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{name:.<40} {status}")
    
    print("\n" + "="*60)
    print(f"Results: {passed}/{total} tests passed ({passed/total*100:.0f}%)")
    print("="*60)
    
    if passed == total:
        print("\n🎉 All tests passed! Integration successful!")
        print("✓ Existing features still work")
        print("✓ New features integrated properly")
        print("✓ No breaking changes detected")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        print("Please review errors above")
    
    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
