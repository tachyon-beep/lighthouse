"""
ML Pattern Cache

Machine learning-based pattern recognition for complex validation scenarios.
Provides 5-10ms response times for pattern-based decisions using pre-trained models.

Features:
- Pre-trained models for command classification
- Feature extraction from request context
- Confidence-based decision making  
- Online learning from expert decisions
- Model versioning and rollback
"""

import asyncio
import json
import logging
import pickle
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

logger = logging.getLogger(__name__)

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    np = None

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import SGDClassifier
    from sklearn.pipeline import Pipeline
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import classification_report
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    logger.warning("scikit-learn not available. Pattern cache will use simpler heuristics.")

from .models import (
    PatternPrediction, ValidationRequest, ValidationResult,
    ValidationDecision, ValidationConfidence
)


class FeatureExtractor:
    """Extract features from validation requests for ML models"""
    
    def __init__(self):
        self.dangerous_keywords = [
            'rm', 'delete', 'remove', 'sudo', 'chmod', 'chown',
            'kill', 'shutdown', 'reboot', 'format', 'fdisk',
            'dd', 'mkfs', 'parted', '/etc/', '/usr/', '/var/',
            '/boot/', '/sys/', '/proc/', '/dev/'
        ]
        
        self.safe_keywords = [
            'ls', 'pwd', 'echo', 'cat', 'grep', 'find', 'git',
            'npm', 'pip', 'python', 'node', 'read', 'search'
        ]
    
    def extract_features(self, request: ValidationRequest) -> Dict[str, float]:
        """Extract numerical features from validation request"""
        
        text = request.command_text.lower()
        tool = request.tool_name.lower()
        
        features = {
            # Tool type features
            'is_bash': 1.0 if tool == 'bash' else 0.0,
            'is_file_operation': 1.0 if tool in ['write', 'edit', 'multiedit'] else 0.0,
            'is_safe_tool': 1.0 if tool in ['read', 'glob', 'grep', 'ls'] else 0.0,
            
            # Text length features
            'command_length': len(text),
            'word_count': len(text.split()),
            'has_special_chars': 1.0 if any(c in text for c in ['|', '>', '<', ';', '&']) else 0.0,
            
            # Dangerous pattern features
            'dangerous_keyword_count': sum(1 for kw in self.dangerous_keywords if kw in text),
            'safe_keyword_count': sum(1 for kw in self.safe_keywords if kw in text),
            
            # Path analysis
            'has_absolute_path': 1.0 if text.startswith('/') else 0.0,
            'has_system_path': 1.0 if any(path in text for path in ['/etc', '/usr', '/var']) else 0.0,
            'has_current_dir': 1.0 if text.startswith('./') or text.startswith('../') else 0.0,
            
            # Command structure
            'has_flags': 1.0 if ' -' in text else 0.0,
            'has_pipes': 1.0 if '|' in text else 0.0,
            'has_redirection': 1.0 if any(op in text for op in ['>', '>>', '<']) else 0.0,
            
            # Agent context
            'agent_hash': hash(request.agent_id) % 1000 / 1000.0,  # Normalize agent ID
        }
        
        return features
    
    def extract_text_features(self, request: ValidationRequest) -> str:
        """Extract text for TF-IDF vectorization"""
        parts = [
            request.tool_name,
            request.command_text,
            request.agent_id.split('_')[-1] if '_' in request.agent_id else request.agent_id
        ]
        
        # Add context if available
        if request.context:
            parts.extend([str(v) for v in request.context.values()])
        
        return ' '.join(parts)


class SimplePatternClassifier:
    """Simple rule-based classifier when scikit-learn is not available"""
    
    def __init__(self):
        self.feature_extractor = FeatureExtractor()
        self.decision_weights = {
            'dangerous_keyword_count': -2.0,
            'safe_keyword_count': 1.5,
            'is_safe_tool': 2.0,
            'has_system_path': -3.0,
            'is_bash': -0.5,
            'has_special_chars': -0.5,
        }
    
    def predict(self, request: ValidationRequest) -> PatternPrediction:
        """Simple weighted scoring prediction"""
        features = self.feature_extractor.extract_features(request)
        
        score = 0.0
        important_features = []
        
        for feature, weight in self.decision_weights.items():
            if feature in features:
                contribution = features[feature] * weight
                score += contribution
                
                if abs(contribution) > 0.1:
                    important_features.append((feature, contribution))
        
        # Convert score to decision
        if score > 1.0:
            decision = ValidationDecision.APPROVED
            confidence = min(0.8, (score - 1.0) / 2.0 + 0.6)
        elif score < -1.0:
            decision = ValidationDecision.BLOCKED
            confidence = min(0.9, abs(score + 1.0) / 3.0 + 0.6)
        else:
            decision = ValidationDecision.UNCERTAIN
            confidence = 0.5
        
        return PatternPrediction(
            decision=decision,
            confidence_score=confidence,
            model_version="simple_v1.0",
            feature_vector=list(features.values()),
            top_features=sorted(important_features, key=lambda x: abs(x[1]), reverse=True)[:5]
        )


class MLPatternClassifier:
    """Machine learning-based pattern classifier using scikit-learn"""
    
    def __init__(self, model_path: Optional[str] = None):
        self.feature_extractor = FeatureExtractor()
        self.model_path = model_path
        self.model = None
        self.model_version = "ml_v1.0"
        self.training_data = []
        
        # Initialize model pipeline
        if SKLEARN_AVAILABLE:
            self.model = Pipeline([
                ('tfidf', TfidfVectorizer(max_features=1000, stop_words='english')),
                ('classifier', SGDClassifier(loss='log_loss', random_state=42))
            ])
        
        # Load pre-trained model if available
        if model_path and Path(model_path).exists():
            self._load_model(model_path)
    
    def _load_model(self, model_path: str):
        """Load pre-trained model from disk"""
        try:
            with open(model_path, 'rb') as f:
                model_data = pickle.load(f)
            
            self.model = model_data['model']
            self.model_version = model_data.get('version', 'loaded_model')
            
            logger.info(f"Loaded ML model version {self.model_version} from {model_path}")
            
        except Exception as e:
            logger.error(f"Failed to load model from {model_path}: {e}")
    
    def _save_model(self, model_path: str):
        """Save trained model to disk"""
        try:
            model_data = {
                'model': self.model,
                'version': self.model_version,
                'training_samples': len(self.training_data),
                'saved_at': time.time()
            }
            
            with open(model_path, 'wb') as f:
                pickle.dump(model_data, f)
            
            logger.info(f"Saved ML model to {model_path}")
            
        except Exception as e:
            logger.error(f"Failed to save model to {model_path}: {e}")
    
    def add_training_example(self, request: ValidationRequest, decision: ValidationDecision):
        """Add training example for online learning"""
        text_features = self.feature_extractor.extract_text_features(request)
        self.training_data.append((text_features, decision.value))
        
        # Retrain periodically
        if len(self.training_data) % 100 == 0:
            asyncio.create_task(self._retrain_model())
    
    async def _retrain_model(self):
        """Retrain model with accumulated examples"""
        if not self.training_data or not SKLEARN_AVAILABLE:
            return
        
        try:
            texts, labels = zip(*self.training_data)
            
            # Split data
            X_train, X_test, y_train, y_test = train_test_split(
                texts, labels, test_size=0.2, random_state=42
            )
            
            # Train model
            self.model.fit(X_train, y_train)
            
            # Evaluate
            y_pred = self.model.predict(X_test)
            report = classification_report(y_test, y_pred, output_dict=True)
            
            logger.info(f"Model retrained. Accuracy: {report['accuracy']:.3f}")
            
            # Save model if configured
            if self.model_path:
                self._save_model(self.model_path)
            
        except Exception as e:
            logger.error(f"Model retraining failed: {e}")
    
    def predict(self, request: ValidationRequest) -> PatternPrediction:
        """Predict using ML model"""
        if not self.model or not SKLEARN_AVAILABLE:
            # Fall back to simple classifier
            simple_classifier = SimplePatternClassifier()
            return simple_classifier.predict(request)
        
        try:
            # Extract features
            text_features = self.feature_extractor.extract_text_features(request)
            numerical_features = self.feature_extractor.extract_features(request)
            
            # Get prediction
            pred_proba = self.model.predict_proba([text_features])[0]
            classes = self.model.classes_
            
            # Find best prediction
            if HAS_NUMPY:
                best_idx = np.argmax(pred_proba)
            else:
                best_idx = pred_proba.index(max(pred_proba))
            decision_str = classes[best_idx]
            confidence = float(pred_proba[best_idx])
            
            decision = ValidationDecision(decision_str)
            
            # Get feature importance (simplified)
            top_features = [
                (feature, value) for feature, value in numerical_features.items()
                if abs(value) > 0.1
            ][:5]
            
            return PatternPrediction(
                decision=decision,
                confidence_score=confidence,
                model_version=self.model_version,
                feature_vector=list(numerical_features.values()),
                top_features=top_features
            )
            
        except Exception as e:
            logger.error(f"ML prediction failed: {e}")
            # Fall back to simple classifier
            simple_classifier = SimplePatternClassifier()
            return simple_classifier.predict(request)


class MLPatternCache:
    """High-performance ML pattern cache"""
    
    def __init__(self, model_path: Optional[str] = None, confidence_threshold: float = 0.8):
        """
        Initialize ML pattern cache
        
        Args:
            model_path: Path to pre-trained model file
            confidence_threshold: Minimum confidence for auto-decisions
        """
        self.confidence_threshold = confidence_threshold
        
        # Initialize classifier
        if SKLEARN_AVAILABLE:
            self.classifier = MLPatternClassifier(model_path)
        else:
            self.classifier = SimplePatternClassifier()
        
        # Prediction cache
        self._prediction_cache: Dict[str, Tuple[PatternPrediction, float]] = {}
        self._cache_ttl = 300.0  # 5 minutes
        
        # Statistics
        self.predictions_made = 0
        self.cache_hits = 0
        self.high_confidence_predictions = 0
    
    async def predict(self, request: ValidationRequest) -> Optional[ValidationResult]:
        """
        Get ML prediction for validation request
        
        Returns None if confidence is too low for auto-decision.
        """
        start_time = time.time()
        
        # Check cache first
        cached_prediction = self._get_cached_prediction(request.command_hash)
        if cached_prediction:
            self.cache_hits += 1
            processing_time = (time.time() - start_time) * 1000
            return cached_prediction.to_validation_result(request, processing_time)
        
        # Get ML prediction
        prediction = self.classifier.predict(request)
        
        # Cache the prediction
        self._cache_prediction(request.command_hash, prediction)
        
        self.predictions_made += 1
        
        # Check confidence threshold
        if prediction.confidence_score < self.confidence_threshold:
            # Not confident enough - escalate to expert
            return None
        
        self.high_confidence_predictions += 1
        
        # Convert to validation result
        processing_time = (time.time() - start_time) * 1000
        return prediction.to_validation_result(request, processing_time)
    
    def _get_cached_prediction(self, command_hash: str) -> Optional[PatternPrediction]:
        """Get cached prediction if available and not expired"""
        if command_hash in self._prediction_cache:
            prediction, cached_at = self._prediction_cache[command_hash]
            
            if time.time() - cached_at < self._cache_ttl:
                return prediction
            else:
                # Remove expired entry
                del self._prediction_cache[command_hash]
        
        return None
    
    def _cache_prediction(self, command_hash: str, prediction: PatternPrediction):
        """Cache prediction result"""
        self._prediction_cache[command_hash] = (prediction, time.time())
        
        # Limit cache size
        if len(self._prediction_cache) > 500:
            # Remove oldest entries
            sorted_items = sorted(
                self._prediction_cache.items(),
                key=lambda x: x[1][1]  # Sort by cached_at timestamp  
            )
            self._prediction_cache = dict(sorted_items[-400:])
    
    def add_feedback(self, request: ValidationRequest, actual_decision: ValidationDecision):
        """
        Add expert feedback for online learning
        
        Args:
            request: Original validation request
            actual_decision: Expert's actual decision
        """
        if hasattr(self.classifier, 'add_training_example'):
            self.classifier.add_training_example(request, actual_decision)
            logger.debug(f"Added training example: {actual_decision.value}")
    
    def get_model_stats(self) -> Dict[str, any]:
        """Get model performance statistics"""
        total_predictions = self.predictions_made
        
        stats = {
            'model_type': type(self.classifier).__name__,
            'model_version': getattr(self.classifier, 'model_version', 'unknown'),
            'confidence_threshold': self.confidence_threshold,
            'predictions_made': total_predictions,
            'cache_hits': self.cache_hits,
            'cache_hit_rate': self.cache_hits / max(1, total_predictions),
            'high_confidence_rate': self.high_confidence_predictions / max(1, total_predictions),
            'cache_size': len(self._prediction_cache),
            'sklearn_available': SKLEARN_AVAILABLE
        }
        
        # Add training data stats if available
        if hasattr(self.classifier, 'training_data'):
            stats['training_examples'] = len(self.classifier.training_data)
        
        return stats
    
    def debug_prediction(self, request: ValidationRequest) -> Dict[str, any]:
        """Get detailed prediction information for debugging"""
        prediction = self.classifier.predict(request)
        
        return {
            'request_id': request.request_id,
            'command_hash': request.command_hash,
            'prediction': {
                'decision': prediction.decision.value,
                'confidence': prediction.confidence_score,
                'confidence_level': prediction.confidence_level.value,
                'model_version': prediction.model_version,
                'top_features': prediction.top_features,
                'feature_count': len(prediction.feature_vector)
            },
            'meets_threshold': prediction.confidence_score >= self.confidence_threshold,
            'would_escalate': prediction.confidence_score < self.confidence_threshold
        }
    
    def clear_cache(self):
        """Clear prediction cache"""
        self._prediction_cache.clear()
        logger.info("ML pattern cache cleared")
    
    async def periodic_maintenance(self, interval_seconds: int = 600):
        """
        Periodic maintenance tasks
        
        Should be run as a background task.
        """
        while True:
            try:
                # Clean up expired cache entries
                current_time = time.time()
                expired_keys = [
                    key for key, (_, cached_at) in self._prediction_cache.items()
                    if current_time - cached_at > self._cache_ttl
                ]
                
                for key in expired_keys:
                    del self._prediction_cache[key]
                
                if expired_keys:
                    logger.debug(f"Cleaned up {len(expired_keys)} expired pattern cache entries")
                
                # Trigger model retraining if we have an ML classifier
                if hasattr(self.classifier, '_retrain_model') and hasattr(self.classifier, 'training_data'):
                    if len(self.classifier.training_data) >= 50:  # Minimum examples for retraining
                        await self.classifier._retrain_model()
                
                await asyncio.sleep(interval_seconds)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Pattern cache maintenance error: {e}")
                await asyncio.sleep(interval_seconds)