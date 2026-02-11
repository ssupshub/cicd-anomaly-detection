"""
Ensemble Anomaly Detector
Combines multiple models for improved accuracy and confidence scoring
"""

import numpy as np
from typing import List, Dict, Tuple, Optional
import logging
import json
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EnsembleDetector:
    """
    Ensemble detector combining multiple anomaly detection methods
    Uses voting and weighted confidence to reduce false positives
    """
    
    def __init__(self):
        self.detectors = {}
        self.weights = {}
        self.is_trained = False
        self.performance_history = []
        
    def add_detector(self, name: str, detector, weight: float = 1.0):
        """
        Add a detector to the ensemble
        
        Args:
            name: Detector identifier
            detector: Detector instance (must have train() and predict() methods)
            weight: Voting weight (higher = more influential)
        """
        self.detectors[name] = detector
        self.weights[name] = weight
        logger.info(f"Added detector '{name}' with weight {weight}")
    
    def train(self, data: List[Dict]) -> Dict:
        """
        Train all detectors in the ensemble
        
        Args:
            data: Training data
            
        Returns:
            Training statistics for each detector
        """
        if not self.detectors:
            raise ValueError("No detectors added to ensemble")
        
        logger.info(f"Training ensemble with {len(self.detectors)} detectors...")
        
        results = {}
        
        for name, detector in self.detectors.items():
            try:
                logger.info(f"Training {name}...")
                stats = detector.train(data)
                results[name] = {
                    'status': 'success',
                    'stats': stats
                }
            except Exception as e:
                logger.error(f"Error training {name}: {e}")
                results[name] = {
                    'status': 'failed',
                    'error': str(e)
                }
        
        self.is_trained = True
        
        return {
            'ensemble_size': len(self.detectors),
            'successful': sum(1 for r in results.values() if r['status'] == 'success'),
            'failed': sum(1 for r in results.values() if r['status'] == 'failed'),
            'detectors': results
        }
    
    def predict(self, data: List[Dict]) -> Tuple[List[Dict], Dict]:
        """
        Predict using ensemble voting
        
        Args:
            data: Data to analyze
            
        Returns:
            Tuple of (anomalies, voting_details)
        """
        if not self.is_trained:
            raise ValueError("Ensemble must be trained before making predictions")
        
        # Collect predictions from all detectors
        all_predictions = {}
        
        for name, detector in self.detectors.items():
            try:
                # Different detectors have different interfaces
                if hasattr(detector, 'detect_statistical_anomalies'):
                    # Statistical detector
                    predictions = detector.detect_statistical_anomalies(data, threshold=2.5)
                elif hasattr(detector, 'predict'):
                    # ML detector (Isolation Forest)
                    preds, scores = detector.predict(data)
                    predictions = self._format_ml_predictions(data, preds, scores)
                elif hasattr(detector, 'detect_anomaly_from_prediction'):
                    # LSTM predictor
                    predictions = self._format_lstm_predictions(detector, data)
                else:
                    logger.warning(f"Detector {name} has unknown interface")
                    continue
                
                all_predictions[name] = predictions
                
            except Exception as e:
                logger.error(f"Error in {name} prediction: {e}")
                all_predictions[name] = []
        
        # Perform ensemble voting
        ensemble_anomalies = self._ensemble_vote(data, all_predictions)
        
        # Calculate voting statistics
        voting_stats = self._calculate_voting_stats(all_predictions, ensemble_anomalies)
        
        return ensemble_anomalies, voting_stats
    
    def _format_ml_predictions(self, data: List[Dict], predictions: np.ndarray, scores: np.ndarray) -> List[Dict]:
        """Format ML model predictions to standard format"""
        anomalies = []
        
        for i, (pred, score) in enumerate(zip(predictions, scores)):
            if pred == -1:  # Anomaly
                anomalies.append({
                    'index': i,
                    'score': float(abs(score)),
                    'data': data[i],
                    'method': 'ml'
                })
        
        return anomalies
    
    def _format_lstm_predictions(self, detector, data: List[Dict]) -> List[Dict]:
        """Format LSTM predictions to standard format"""
        anomalies = []
        
        for i in range(len(data) - 10):  # Need sequence
            recent = data[max(0, i-20):i+1]
            
            try:
                predictions = detector.predict_next(recent)
                detected = detector.detect_anomaly_from_prediction(data[i+1], predictions)
                
                if detected:
                    anomalies.append({
                        'index': i+1,
                        'score': max(a['deviation_pct']/100 for a in detected),
                        'data': data[i+1],
                        'details': detected,
                        'method': 'lstm'
                    })
            except:
                continue
        
        return anomalies
    
    def _ensemble_vote(self, data: List[Dict], all_predictions: Dict[str, List[Dict]]) -> List[Dict]:
        """
        Perform weighted voting across all detectors
        
        Args:
            data: Original data
            all_predictions: Predictions from each detector
            
        Returns:
            Consensus anomalies with confidence scores
        """
        # Track votes for each data point
        votes = {}
        
        for detector_name, predictions in all_predictions.items():
            weight = self.weights.get(detector_name, 1.0)
            
            for pred in predictions:
                idx = pred['index']
                score = pred.get('score', 1.0)
                
                if idx not in votes:
                    votes[idx] = {
                        'index': idx,
                        'data': data[idx] if idx < len(data) else pred.get('data', {}),
                        'votes': 0,
                        'weighted_votes': 0,
                        'detectors': [],
                        'scores': []
                    }
                
                votes[idx]['votes'] += 1
                votes[idx]['weighted_votes'] += weight
                votes[idx]['detectors'].append(detector_name)
                votes[idx]['scores'].append(score)
        
        # Calculate consensus
        ensemble_anomalies = []
        total_weight = sum(self.weights.values())
        
        for idx, vote_data in votes.items():
            # Require at least 50% weighted vote
            confidence = vote_data['weighted_votes'] / total_weight
            
            if confidence >= 0.5:  # Consensus threshold
                avg_score = np.mean(vote_data['scores'])
                
                ensemble_anomalies.append({
                    'index': idx,
                    'data': vote_data['data'],
                    'confidence': float(confidence),
                    'avg_score': float(avg_score),
                    'num_detectors': vote_data['votes'],
                    'detectors_agreed': vote_data['detectors'],
                    'severity': self._calculate_severity(confidence, avg_score)
                })
        
        # Sort by confidence
        ensemble_anomalies.sort(key=lambda x: x['confidence'], reverse=True)
        
        return ensemble_anomalies
    
    def _calculate_severity(self, confidence: float, score: float) -> str:
        """Calculate anomaly severity based on confidence and score"""
        if confidence >= 0.8 and score >= 0.7:
            return 'critical'
        elif confidence >= 0.65 and score >= 0.5:
            return 'high'
        elif confidence >= 0.5 and score >= 0.3:
            return 'medium'
        else:
            return 'low'
    
    def _calculate_voting_stats(self, all_predictions: Dict, ensemble_anomalies: List[Dict]) -> Dict:
        """Calculate voting statistics"""
        total_predictions = sum(len(preds) for preds in all_predictions.values())
        
        # Count agreements
        agreement_counts = {}
        for anomaly in ensemble_anomalies:
            num_agreed = anomaly['num_detectors']
            agreement_counts[num_agreed] = agreement_counts.get(num_agreed, 0) + 1
        
        return {
            'total_individual_detections': total_predictions,
            'ensemble_detections': len(ensemble_anomalies),
            'reduction_rate': 1 - (len(ensemble_anomalies) / max(total_predictions, 1)),
            'agreement_distribution': agreement_counts,
            'detector_contributions': {
                name: len(preds) for name, preds in all_predictions.items()
            }
        }
    
    def update_weights(self, feedback: List[Dict]):
        """
        Update detector weights based on performance feedback
        
        Args:
            feedback: List of feedback items with detector performance
        """
        if not feedback:
            return
        
        # Calculate performance scores
        performance = {name: [] for name in self.detectors.keys()}
        
        for item in feedback:
            detector = item.get('detector')
            correct = item.get('correct', False)
            
            if detector in performance:
                performance[detector].append(1.0 if correct else 0.0)
        
        # Update weights based on accuracy
        for name, scores in performance.items():
            if scores:
                accuracy = np.mean(scores)
                # Adjust weight: higher accuracy = higher weight
                self.weights[name] = max(0.1, min(2.0, accuracy * 2))
                logger.info(f"Updated {name} weight to {self.weights[name]:.2f} (accuracy: {accuracy:.2%})")
        
        self.performance_history.append({
            'timestamp': datetime.now().isoformat(),
            'weights': self.weights.copy(),
            'performance': {k: np.mean(v) if v else 0 for k, v in performance.items()}
        })
    
    def get_performance_report(self) -> Dict:
        """Get performance report for all detectors"""
        if not self.performance_history:
            return {'message': 'No performance data available'}
        
        latest = self.performance_history[-1]
        
        return {
            'current_weights': self.weights,
            'latest_performance': latest['performance'],
            'history_length': len(self.performance_history),
            'timestamp': latest['timestamp']
        }
    
    def save_ensemble(self, directory: str):
        """Save ensemble configuration"""
        import os
        os.makedirs(directory, exist_ok=True)
        
        metadata = {
            'weights': self.weights,
            'detector_names': list(self.detectors.keys()),
            'is_trained': self.is_trained,
            'performance_history': self.performance_history[-10:]  # Last 10
        }
        
        filepath = os.path.join(directory, 'ensemble_metadata.json')
        with open(filepath, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        # Save individual detectors
        for name, detector in self.detectors.items():
            if hasattr(detector, 'save_model'):
                try:
                    detector.save_model(os.path.join(directory, f'{name}_model'))
                except Exception as e:
                    logger.warning(f"Could not save {name}: {e}")
        
        logger.info(f"Ensemble saved to {directory}")
    
    def load_ensemble(self, directory: str):
        """Load ensemble configuration"""
        import os
        
        filepath = os.path.join(directory, 'ensemble_metadata.json')
        with open(filepath, 'r') as f:
            metadata = json.load(f)
        
        self.weights = metadata['weights']
        self.is_trained = metadata['is_trained']
        self.performance_history = metadata.get('performance_history', [])
        
        # Load individual detectors
        for name in self.detectors.keys():
            if hasattr(self.detectors[name], 'load_model'):
                try:
                    self.detectors[name].load_model(os.path.join(directory, f'{name}_model'))
                except Exception as e:
                    logger.warning(f"Could not load {name}: {e}")
        
        logger.info(f"Ensemble loaded from {directory}")


def main():
    """Example usage"""
    from ml.anomaly_detector import AnomalyDetector
    from ml.lstm_predictor import LSTMPredictor
    
    # Generate mock data
    np.random.seed(42)
    
    normal_data = []
    for i in range(150):
        normal_data.append({
            'duration': np.random.normal(300, 50),
            'queue_time': np.random.normal(10, 3),
            'test_count': np.random.randint(80, 120),
            'failure_count': np.random.randint(0, 3),
            'failure_rate': np.random.uniform(0, 0.05),
            'step_count': np.random.randint(5, 15),
            'job_count': 1,
            'failed_jobs': 0,
        })
    
    # Add anomalies
    anomaly_data = []
    for i in range(15):
        anomaly_data.append({
            'duration': np.random.normal(800, 100),
            'queue_time': np.random.normal(50, 10),
            'test_count': np.random.randint(80, 120),
            'failure_count': np.random.randint(10, 20),
            'failure_rate': np.random.uniform(0.1, 0.3),
            'step_count': np.random.randint(5, 15),
            'job_count': 1,
            'failed_jobs': 1,
        })
    
    all_data = normal_data + anomaly_data
    np.random.shuffle(all_data)
    
    # Create ensemble
    ensemble = EnsembleDetector()
    
    # Add detectors
    isolation_forest = AnomalyDetector(contamination=0.1)
    lstm_pred = LSTMPredictor(sequence_length=10)
    
    ensemble.add_detector('isolation_forest', isolation_forest, weight=1.2)
    ensemble.add_detector('lstm', lstm_pred, weight=0.8)
    
    # Train
    print("Training ensemble...")
    train_stats = ensemble.train(all_data[:140])
    print(json.dumps(train_stats, indent=2))
    
    # Predict
    print("\n" + "="*60)
    print("Ensemble Predictions:")
    print("="*60)
    
    test_data = all_data[140:]
    anomalies, voting_stats = ensemble.predict(test_data)
    
    print(f"\nDetected {len(anomalies)} anomalies")
    print(f"\nVoting Statistics:")
    print(json.dumps(voting_stats, indent=2))
    
    print(f"\nTop 5 Anomalies:")
    for i, anomaly in enumerate(anomalies[:5], 1):
        print(f"\n{i}. Confidence: {anomaly['confidence']:.2%}")
        print(f"   Severity: {anomaly['severity']}")
        print(f"   Detectors agreed: {anomaly['detectors_agreed']}")
        print(f"   Score: {anomaly['avg_score']:.3f}")


if __name__ == "__main__":
    main()
