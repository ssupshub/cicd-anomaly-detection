"""
LSTM Time Series Predictor
Predicts next build duration and detects anomalies based on temporal patterns
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional
import logging
import json
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class LSTMPredictor:
    """
    LSTM-based predictor for CI/CD metrics
    Predicts next build duration, queue time, and failure probability
    """
    
    def __init__(self, sequence_length: int = 10, features: List[str] = None):
        """
        Initialize LSTM predictor
        
        Args:
            sequence_length: Number of previous builds to use for prediction
            features: List of features to predict
        """
        self.sequence_length = sequence_length
        self.features = features or ['duration', 'queue_time', 'test_count', 'failure_count']
        self.models = {}
        self.scalers = {}
        self.is_trained = False
        self.history = []
        
        # Fallback to statistical methods when TensorFlow not available
        self.use_statistical_fallback = True
        
        try:
            import tensorflow as tf
            from tensorflow import keras
            self.tf = tf
            self.keras = keras
            self.use_statistical_fallback = False
            logger.info("TensorFlow available, using LSTM models")
        except ImportError:
            logger.warning("TensorFlow not available, using statistical fallback")
    
    def prepare_sequences(self, data: List[Dict]) -> Tuple[np.ndarray, np.ndarray]:
        """
        Prepare sequential data for LSTM
        
        Args:
            data: List of build metrics
            
        Returns:
            X: Input sequences, y: Target values
        """
        df = pd.DataFrame(data)
        
        # Sort by timestamp
        if 'timestamp' in df.columns:
            df = df.sort_values('timestamp')
        
        sequences = []
        targets = []
        
        for feature in self.features:
            if feature not in df.columns:
                continue
                
            values = df[feature].values
            
            for i in range(len(values) - self.sequence_length):
                seq = values[i:i + self.sequence_length]
                target = values[i + self.sequence_length]
                sequences.append(seq)
                targets.append(target)
        
        if not sequences:
            return np.array([]), np.array([])
        
        X = np.array(sequences).reshape(-1, self.sequence_length, 1)
        y = np.array(targets)
        
        return X, y
    
    def build_lstm_model(self, input_shape: Tuple) -> 'keras.Model':
        """Build LSTM model architecture"""
        if self.use_statistical_fallback:
            return None
            
        model = self.keras.Sequential([
            self.keras.layers.LSTM(50, activation='relu', input_shape=input_shape, return_sequences=True),
            self.keras.layers.Dropout(0.2),
            self.keras.layers.LSTM(50, activation='relu'),
            self.keras.layers.Dropout(0.2),
            self.keras.layers.Dense(25, activation='relu'),
            self.keras.layers.Dense(1)
        ])
        
        model.compile(optimizer='adam', loss='mse', metrics=['mae'])
        return model
    
    def train_statistical_model(self, data: List[Dict]) -> Dict:
        """
        Train statistical models as fallback
        Uses exponential moving average and seasonal decomposition
        """
        logger.info("Training statistical fallback models...")
        
        df = pd.DataFrame(data)
        stats = {}
        
        for feature in self.features:
            if feature not in df.columns:
                continue
            
            values = df[feature].values
            
            # Calculate statistics
            stats[feature] = {
                'mean': float(np.mean(values)),
                'std': float(np.std(values)),
                'median': float(np.median(values)),
                'ema': self._calculate_ema(values),
                'trend': self._calculate_trend(values),
                'last_values': values[-self.sequence_length:].tolist()
            }
        
        self.history = data[-100:]  # Keep last 100 for predictions
        self.statistics = stats
        self.is_trained = True
        
        return {
            'method': 'statistical',
            'features': list(stats.keys()),
            'samples': len(data)
        }
    
    def _calculate_ema(self, values: np.ndarray, alpha: float = 0.3) -> float:
        """Calculate Exponential Moving Average"""
        ema = values[0]
        for value in values[1:]:
            ema = alpha * value + (1 - alpha) * ema
        return float(ema)
    
    def _calculate_trend(self, values: np.ndarray) -> float:
        """Calculate simple trend (slope of linear regression)"""
        if len(values) < 2:
            return 0.0
        
        x = np.arange(len(values))
        coefficients = np.polyfit(x, values, 1)
        return float(coefficients[0])
    
    def train(self, data: List[Dict], epochs: int = 50, batch_size: int = 32) -> Dict:
        """
        Train the predictor
        
        Args:
            data: Historical build data
            epochs: Number of training epochs (for LSTM)
            batch_size: Batch size (for LSTM)
            
        Returns:
            Training statistics
        """
        if len(data) < self.sequence_length + 10:
            raise ValueError(f"Need at least {self.sequence_length + 10} samples to train")
        
        # Use statistical fallback if TensorFlow unavailable or data too small
        if self.use_statistical_fallback or len(data) < 100:
            return self.train_statistical_model(data)
        
        logger.info(f"Training LSTM models with {len(data)} samples...")
        
        X, y = self.prepare_sequences(data)
        
        if len(X) == 0:
            return self.train_statistical_model(data)
        
        # Split train/validation
        split_idx = int(len(X) * 0.8)
        X_train, X_val = X[:split_idx], X[split_idx:]
        y_train, y_val = y[:split_idx], y[split_idx:]
        
        # Build and train model
        model = self.build_lstm_model((self.sequence_length, 1))
        
        history = model.fit(
            X_train, y_train,
            validation_data=(X_val, y_val),
            epochs=epochs,
            batch_size=batch_size,
            verbose=0
        )
        
        self.models['lstm'] = model
        self.is_trained = True
        self.history = data[-100:]
        
        final_loss = history.history['loss'][-1]
        final_val_loss = history.history['val_loss'][-1]
        
        return {
            'method': 'lstm',
            'samples': len(data),
            'train_loss': float(final_loss),
            'val_loss': float(final_val_loss),
            'epochs': epochs
        }
    
    def predict_next(self, recent_builds: List[Dict], job_name: str = None) -> Dict:
        """
        Predict metrics for next build
        
        Args:
            recent_builds: Recent build history
            job_name: Optional job name for job-specific prediction
            
        Returns:
            Predicted metrics with confidence intervals
        """
        if not self.is_trained:
            raise ValueError("Model must be trained before making predictions")
        
        # Statistical prediction
        if self.use_statistical_fallback or 'lstm' not in self.models:
            return self._predict_statistical(recent_builds, job_name)
        
        # LSTM prediction
        predictions = {}
        
        for feature in self.features:
            df = pd.DataFrame(recent_builds)
            if feature not in df.columns:
                continue
            
            values = df[feature].values
            if len(values) < self.sequence_length:
                continue
            
            # Get last sequence
            sequence = values[-self.sequence_length:]
            X = sequence.reshape(1, self.sequence_length, 1)
            
            # Predict
            pred = self.models['lstm'].predict(X, verbose=0)[0][0]
            
            predictions[feature] = {
                'predicted': float(pred),
                'actual_last': float(values[-1]),
                'confidence': self._calculate_confidence(values, pred)
            }
        
        return predictions
    
    def _predict_statistical(self, recent_builds: List[Dict], job_name: str = None) -> Dict:
        """Statistical prediction using EMA and trend"""
        predictions = {}
        
        df = pd.DataFrame(recent_builds)
        
        for feature in self.features:
            if feature not in df.columns or feature not in self.statistics:
                continue
            
            stats = self.statistics[feature]
            values = df[feature].values
            
            if len(values) == 0:
                continue
            
            # Predict using EMA + trend
            ema = self._calculate_ema(values)
            trend = self._calculate_trend(values)
            predicted = ema + trend
            
            # Bounds based on historical std
            std = stats['std']
            
            predictions[feature] = {
                'predicted': float(predicted),
                'lower_bound': float(predicted - 2 * std),
                'upper_bound': float(predicted + 2 * std),
                'actual_last': float(values[-1]),
                'confidence': 0.7  # Lower confidence for statistical method
            }
        
        return predictions
    
    def _calculate_confidence(self, values: np.ndarray, prediction: float) -> float:
        """Calculate prediction confidence based on historical variance"""
        std = np.std(values)
        mean = np.mean(values)
        
        if std == 0:
            return 0.9
        
        # Lower confidence if prediction deviates significantly from mean
        deviation = abs(prediction - mean) / std
        confidence = max(0.3, 1.0 - (deviation * 0.1))
        
        return float(min(0.95, confidence))
    
    def detect_anomaly_from_prediction(self, actual: Dict, predicted: Dict) -> List[Dict]:
        """
        Detect anomalies by comparing actual vs predicted values
        
        Args:
            actual: Actual build metrics
            predicted: Predicted metrics
            
        Returns:
            List of detected anomalies
        """
        anomalies = []
        
        for feature, pred_data in predicted.items():
            if feature not in actual:
                continue
            
            actual_value = actual[feature]
            predicted_value = pred_data['predicted']
            confidence = pred_data.get('confidence', 0.5)
            
            # Calculate deviation
            if predicted_value != 0:
                deviation_pct = abs(actual_value - predicted_value) / predicted_value
            else:
                deviation_pct = 0
            
            # Anomaly if actual deviates significantly from prediction
            threshold = 0.3  # 30% deviation
            if deviation_pct > threshold and confidence > 0.6:
                anomalies.append({
                    'feature': feature,
                    'actual': float(actual_value),
                    'predicted': float(predicted_value),
                    'deviation_pct': float(deviation_pct * 100),
                    'confidence': float(confidence),
                    'severity': 'high' if deviation_pct > 0.5 else 'medium'
                })
        
        return anomalies
    
    def save_model(self, filepath: str):
        """Save model and statistics"""
        metadata = {
            'sequence_length': self.sequence_length,
            'features': self.features,
            'is_trained': self.is_trained,
            'use_statistical_fallback': self.use_statistical_fallback,
            'statistics': getattr(self, 'statistics', {}),
            'history': self.history[-20:]  # Save recent history
        }
        
        with open(filepath + '_metadata.json', 'w') as f:
            json.dump(metadata, f, indent=2)
        
        # Save LSTM model if available
        if not self.use_statistical_fallback and 'lstm' in self.models:
            self.models['lstm'].save(filepath + '_lstm.h5')
        
        logger.info(f"Model saved to {filepath}")
    
    def load_model(self, filepath: str):
        """Load model and statistics"""
        with open(filepath + '_metadata.json', 'r') as f:
            metadata = json.load(f)
        
        self.sequence_length = metadata['sequence_length']
        self.features = metadata['features']
        self.is_trained = metadata['is_trained']
        self.use_statistical_fallback = metadata['use_statistical_fallback']
        self.statistics = metadata.get('statistics', {})
        self.history = metadata.get('history', [])
        
        # Load LSTM model if available
        if not self.use_statistical_fallback:
            try:
                self.models['lstm'] = self.keras.models.load_model(filepath + '_lstm.h5')
            except:
                logger.warning("Could not load LSTM model, using statistical fallback")
                self.use_statistical_fallback = True
        
        logger.info(f"Model loaded from {filepath}")


def main():
    """Example usage"""
    # Generate mock data
    np.random.seed(42)
    
    builds = []
    base_duration = 300
    
    for i in range(200):
        # Simulate time-based patterns
        hour = i % 24
        day = i // 24
        
        # Peak hours effect
        if 10 <= hour <= 16:
            duration = base_duration + np.random.normal(50, 20)
        else:
            duration = base_duration + np.random.normal(-30, 15)
        
        # Weekly trend
        duration += day * 2  # Gradual increase
        
        builds.append({
            'duration': max(60, duration),
            'queue_time': max(0, np.random.exponential(10) + (hour - 12) * 0.5),
            'test_count': int(np.random.normal(100, 10)),
            'failure_count': int(np.random.poisson(2)),
            'timestamp': f"2024-02-{(day % 28) + 1:02d}T{hour:02d}:00:00"
        })
    
    # Train predictor
    predictor = LSTMPredictor(sequence_length=10)
    stats = predictor.train(builds[:180])
    
    print("Training Results:")
    print(json.dumps(stats, indent=2))
    
    # Make predictions
    print("\n" + "="*60)
    print("Predictions for next builds:")
    print("="*60)
    
    for i in range(180, 190):
        recent = builds[max(0, i-20):i]
        predictions = predictor.predict_next(recent)
        actual = builds[i]
        
        print(f"\nBuild {i}:")
        for feature, pred in predictions.items():
            if feature in actual:
                print(f"  {feature}:")
                print(f"    Predicted: {pred['predicted']:.1f}")
                print(f"    Actual: {actual[feature]:.1f}")
                print(f"    Confidence: {pred['confidence']:.2f}")
        
        # Detect anomalies
        anomalies = predictor.detect_anomaly_from_prediction(actual, predictions)
        if anomalies:
            print(f"  ⚠️  Anomalies detected: {len(anomalies)}")
            for anomaly in anomalies:
                print(f"    - {anomaly['feature']}: {anomaly['deviation_pct']:.1f}% deviation")


if __name__ == "__main__":
    main()
