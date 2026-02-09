"""
Machine Learning Anomaly Detection Model
Uses Isolation Forest and statistical methods to detect anomalies in CI/CD pipelines
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
import joblib
import json
import os
from datetime import datetime
from typing import Dict, List, Tuple, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AnomalyDetector:
    """Detects anomalies in CI/CD pipeline metrics using ML"""
    
    def __init__(self, contamination: float = 0.1, random_state: int = 42):
        """
        Initialize the anomaly detector
        
        Args:
            contamination: Expected proportion of outliers in the dataset
            random_state: Random seed for reproducibility
        """
        self.contamination = contamination
        self.random_state = random_state
        
        self.model = IsolationForest(
            contamination=contamination,
            random_state=random_state,
            n_estimators=100
        )
        
        self.scaler = StandardScaler()
        self.pca = None
        self.feature_names = []
        self.statistics = {}
        self.is_trained = False
        
    def prepare_features(self, data: List[Dict]) -> pd.DataFrame:
        """Convert raw metrics to feature DataFrame"""
        df = pd.DataFrame(data)
        
        # Select numeric features
        numeric_features = [
            'duration', 'queue_time', 'test_count', 'failure_count',
            'failure_rate', 'step_count', 'job_count', 'failed_jobs'
        ]
        
        # Use only available features
        available_features = [f for f in numeric_features if f in df.columns]
        
        # Fill missing values with 0
        for feature in available_features:
            df[feature] = df[feature].fillna(0)
        
        # Add derived features
        if 'duration' in df.columns and 'test_count' in df.columns:
            df['duration_per_test'] = df.apply(
                lambda row: row['duration'] / row['test_count'] if row['test_count'] > 0 else row['duration'],
                axis=1
            )
            available_features.append('duration_per_test')
        
        if 'failure_count' in df.columns and 'test_count' in df.columns:
            df['failure_rate_calculated'] = df.apply(
                lambda row: row['failure_count'] / row['test_count'] if row['test_count'] > 0 else 0,
                axis=1
            )
            if 'failure_rate_calculated' not in available_features:
                available_features.append('failure_rate_calculated')
        
        self.feature_names = available_features
        return df[available_features]
    
    def calculate_statistics(self, features: pd.DataFrame):
        """Calculate statistical metrics for each feature"""
        self.statistics = {
            'mean': features.mean().to_dict(),
            'std': features.std().to_dict(),
            'median': features.median().to_dict(),
            'q25': features.quantile(0.25).to_dict(),
            'q75': features.quantile(0.75).to_dict(),
        }
    
    def train(self, data: List[Dict], use_pca: bool = False, n_components: int = 5) -> Dict:
        """
        Train the anomaly detection model
        
        Args:
            data: List of metric dictionaries
            use_pca: Whether to use PCA for dimensionality reduction
            n_components: Number of PCA components
            
        Returns:
            Training statistics
        """
        logger.info(f"Training model with {len(data)} samples")
        
        if len(data) < 10:
            raise ValueError("Need at least 10 samples to train the model")
        
        # Prepare features
        features = self.prepare_features(data)
        
        logger.info(f"Using features: {self.feature_names}")
        
        # Calculate statistics
        self.calculate_statistics(features)
        
        # Scale features
        scaled_features = self.scaler.fit_transform(features)
        
        # Optional PCA
        if use_pca and len(self.feature_names) > n_components:
            self.pca = PCA(n_components=n_components, random_state=self.random_state)
            scaled_features = self.pca.fit_transform(scaled_features)
            logger.info(f"PCA variance explained: {self.pca.explained_variance_ratio_.sum():.2%}")
        
        # Train model
        self.model.fit(scaled_features)
        self.is_trained = True
        
        # Calculate training statistics
        predictions = self.model.predict(scaled_features)
        anomaly_count = (predictions == -1).sum()
        
        stats = {
            'samples': len(data),
            'features': len(self.feature_names),
            'anomalies_detected': int(anomaly_count),
            'anomaly_rate': float(anomaly_count / len(data)),
            'trained_at': datetime.now().isoformat(),
        }
        
        logger.info(f"Training complete: {stats}")
        return stats
    
    def predict(self, data: List[Dict]) -> Tuple[np.ndarray, np.ndarray]:
        """
        Predict anomalies in new data
        
        Args:
            data: List of metric dictionaries
            
        Returns:
            Tuple of (predictions, anomaly_scores)
            predictions: -1 for anomalies, 1 for normal
            anomaly_scores: Anomaly scores (lower is more anomalous)
        """
        if not self.is_trained:
            raise ValueError("Model must be trained before making predictions")
        
        # Prepare features
        features = self.prepare_features(data)
        
        # Scale features
        scaled_features = self.scaler.transform(features)
        
        # Apply PCA if used during training
        if self.pca is not None:
            scaled_features = self.pca.transform(scaled_features)
        
        # Predict
        predictions = self.model.predict(scaled_features)
        anomaly_scores = self.model.score_samples(scaled_features)
        
        return predictions, anomaly_scores
    
    def detect_statistical_anomalies(self, data: List[Dict], threshold: float = 3.0) -> List[Dict]:
        """
        Detect anomalies using statistical methods (z-score)
        
        Args:
            data: List of metric dictionaries
            threshold: Number of standard deviations for anomaly threshold
            
        Returns:
            List of anomaly reports
        """
        if not self.statistics:
            raise ValueError("Model must be trained before detecting anomalies")
        
        features = self.prepare_features(data)
        anomalies = []
        
        for idx, row in features.iterrows():
            anomaly_features = []
            max_z_score = 0
            
            for feature in self.feature_names:
                value = row[feature]
                mean = self.statistics['mean'][feature]
                std = self.statistics['std'][feature]
                
                if std > 0:
                    z_score = abs((value - mean) / std)
                    if z_score > threshold:
                        anomaly_features.append({
                            'feature': feature,
                            'value': float(value),
                            'expected': float(mean),
                            'std': float(std),
                            'z_score': float(z_score)
                        })
                        max_z_score = max(max_z_score, z_score)
            
            if anomaly_features:
                anomalies.append({
                    'index': int(idx),
                    'max_z_score': float(max_z_score),
                    'anomaly_features': anomaly_features,
                    'data': data[idx] if idx < len(data) else {}
                })
        
        return anomalies
    
    def save_model(self, directory: str):
        """Save the model and scaler to disk"""
        os.makedirs(directory, exist_ok=True)
        
        model_path = os.path.join(directory, 'isolation_forest.pkl')
        scaler_path = os.path.join(directory, 'scaler.pkl')
        stats_path = os.path.join(directory, 'statistics.json')
        
        joblib.dump(self.model, model_path)
        joblib.dump(self.scaler, scaler_path)
        
        if self.pca is not None:
            pca_path = os.path.join(directory, 'pca.pkl')
            joblib.dump(self.pca, pca_path)
        
        # Save metadata
        metadata = {
            'feature_names': self.feature_names,
            'statistics': self.statistics,
            'contamination': self.contamination,
            'is_trained': self.is_trained,
            'has_pca': self.pca is not None,
        }
        
        with open(stats_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        logger.info(f"Model saved to {directory}")
    
    def load_model(self, directory: str):
        """Load the model and scaler from disk"""
        model_path = os.path.join(directory, 'isolation_forest.pkl')
        scaler_path = os.path.join(directory, 'scaler.pkl')
        stats_path = os.path.join(directory, 'statistics.json')
        pca_path = os.path.join(directory, 'pca.pkl')
        
        self.model = joblib.load(model_path)
        self.scaler = joblib.load(scaler_path)
        
        if os.path.exists(pca_path):
            self.pca = joblib.load(pca_path)
        
        with open(stats_path, 'r') as f:
            metadata = json.load(f)
        
        self.feature_names = metadata['feature_names']
        self.statistics = metadata['statistics']
        self.contamination = metadata['contamination']
        self.is_trained = metadata['is_trained']
        
        logger.info(f"Model loaded from {directory}")


def main():
    """Example usage with mock data"""
    # Generate mock training data
    np.random.seed(42)
    
    normal_data = []
    for i in range(200):
        normal_data.append({
            'duration': np.random.normal(300, 50),
            'queue_time': np.random.normal(10, 3),
            'test_count': np.random.randint(80, 120),
            'failure_count': np.random.randint(0, 3),
            'failure_rate': np.random.uniform(0, 0.05),
            'step_count': np.random.randint(5, 15),
            'job_count': np.random.randint(1, 5),
            'failed_jobs': 0,
        })
    
    # Add some anomalies
    anomaly_data = []
    for i in range(20):
        anomaly_data.append({
            'duration': np.random.normal(800, 100),  # Much longer
            'queue_time': np.random.normal(50, 10),  # Long queue
            'test_count': np.random.randint(80, 120),
            'failure_count': np.random.randint(10, 20),  # Many failures
            'failure_rate': np.random.uniform(0.1, 0.3),
            'step_count': np.random.randint(5, 15),
            'job_count': np.random.randint(1, 5),
            'failed_jobs': np.random.randint(1, 3),
        })
    
    all_data = normal_data + anomaly_data
    np.random.shuffle(all_data)
    
    # Train model
    detector = AnomalyDetector(contamination=0.1)
    stats = detector.train(all_data)
    print("Training statistics:", json.dumps(stats, indent=2))
    
    # Test predictions
    test_data = normal_data[:10] + anomaly_data[:5]
    predictions, scores = detector.predict(test_data)
    
    print("\nPredictions:")
    for i, (pred, score) in enumerate(zip(predictions, scores)):
        status = "ANOMALY" if pred == -1 else "NORMAL"
        print(f"Sample {i}: {status} (score: {score:.3f})")
    
    # Statistical anomaly detection
    stat_anomalies = detector.detect_statistical_anomalies(test_data, threshold=2.5)
    print(f"\nStatistical anomalies detected: {len(stat_anomalies)}")
    
    # Save model
    detector.save_model('/home/claude/cicd-anomaly-detection/models')
    print("\nModel saved successfully")


if __name__ == "__main__":
    main()
