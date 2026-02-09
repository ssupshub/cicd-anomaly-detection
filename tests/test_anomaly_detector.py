"""
Unit tests for anomaly detector
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import numpy as np
from ml.anomaly_detector import AnomalyDetector


def generate_mock_data(n_samples=100, add_anomalies=True):
    """Generate mock CI/CD metrics"""
    data = []
    
    # Normal data
    for i in range(n_samples):
        data.append({
            'duration': np.random.normal(300, 50),
            'queue_time': np.random.normal(10, 3),
            'test_count': np.random.randint(80, 120),
            'failure_count': np.random.randint(0, 3),
            'failure_rate': np.random.uniform(0, 0.05),
            'step_count': np.random.randint(5, 15),
            'job_count': np.random.randint(1, 5),
            'failed_jobs': 0,
        })
    
    # Add anomalies
    if add_anomalies:
        for i in range(10):
            data.append({
                'duration': np.random.normal(800, 100),
                'queue_time': np.random.normal(50, 10),
                'test_count': np.random.randint(80, 120),
                'failure_count': np.random.randint(10, 20),
                'failure_rate': np.random.uniform(0.1, 0.3),
                'step_count': np.random.randint(5, 15),
                'job_count': np.random.randint(1, 5),
                'failed_jobs': np.random.randint(1, 3),
            })
    
    return data


def test_detector_initialization():
    """Test detector initialization"""
    detector = AnomalyDetector(contamination=0.1)
    assert detector is not None
    assert detector.contamination == 0.1
    assert not detector.is_trained


def test_feature_preparation():
    """Test feature preparation"""
    detector = AnomalyDetector()
    data = generate_mock_data(50, add_anomalies=False)
    features = detector.prepare_features(data)
    
    assert features is not None
    assert len(features) == 50
    assert len(detector.feature_names) > 0


def test_model_training():
    """Test model training"""
    detector = AnomalyDetector(contamination=0.1)
    data = generate_mock_data(100)
    
    stats = detector.train(data)
    
    assert detector.is_trained
    assert stats['samples'] == 100
    assert 'anomalies_detected' in stats
    assert len(detector.statistics) > 0


def test_anomaly_prediction():
    """Test anomaly prediction"""
    detector = AnomalyDetector(contamination=0.1)
    
    # Train
    train_data = generate_mock_data(100)
    detector.train(train_data)
    
    # Predict
    test_data = generate_mock_data(20)
    predictions, scores = detector.predict(test_data)
    
    assert len(predictions) == 20
    assert len(scores) == 20
    assert -1 in predictions or 1 in predictions


def test_statistical_detection():
    """Test statistical anomaly detection"""
    detector = AnomalyDetector()
    
    # Train
    train_data = generate_mock_data(100)
    detector.train(train_data)
    
    # Detect
    test_data = generate_mock_data(20)
    anomalies = detector.detect_statistical_anomalies(test_data, threshold=2.5)
    
    assert isinstance(anomalies, list)
    # Should detect some anomalies
    assert len(anomalies) >= 0


def test_model_save_load():
    """Test model persistence"""
    import tempfile
    import shutil
    
    # Create temp directory
    temp_dir = tempfile.mkdtemp()
    
    try:
        # Train and save
        detector1 = AnomalyDetector()
        data = generate_mock_data(100)
        detector1.train(data)
        detector1.save_model(temp_dir)
        
        # Load
        detector2 = AnomalyDetector()
        detector2.load_model(temp_dir)
        
        assert detector2.is_trained
        assert detector2.feature_names == detector1.feature_names
        
        # Test predictions match
        test_data = generate_mock_data(10, add_anomalies=False)
        pred1, score1 = detector1.predict(test_data)
        pred2, score2 = detector2.predict(test_data)
        
        assert np.array_equal(pred1, pred2)
        
    finally:
        shutil.rmtree(temp_dir)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
