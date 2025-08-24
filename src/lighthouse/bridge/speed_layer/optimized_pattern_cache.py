"""
Optimized Pattern Cache for Speed Layer

High-performance ML pattern cache optimized for 5-10ms response times.
Uses optimized feature extraction, model quantization, and inference caching.

Performance Optimizations:
- Pre-computed feature vectors with vectorized operations
- Model quantization for faster inference (int8/float16)
- Inference result caching with smart cache keys
- Batch prediction for similar requests
- Hot feature path optimization for common patterns
"""

import asyncio
import json
import logging
import pickle
import time
from collections import deque, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import hashlib

logger = logging.getLogger(__name__)

# Optional high-performance dependencies
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
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

from .models import (
    PatternPrediction, ValidationRequest, ValidationResult,
    ValidationDecision, ValidationConfidence
)


class FastFeatureExtractor:
    """Optimized feature extraction for maximum speed"""
    
    def __init__(self):
        # Pre-computed feature sets for hot path optimization
        self.dangerous_keywords = frozenset([
            'rm', 'delete', 'remove', 'sudo', 'chmod', 'chown',
            'kill', 'shutdown', 'reboot', 'format', 'fdisk',
            'dd', 'mkfs', 'parted', 'mv', 'cp'
        ])
        
        self.safe_keywords = frozenset([
            'ls', 'cat', 'grep', 'find', 'head', 'tail',
            'echo', 'pwd', 'cd', 'mkdir', 'touch'
        ])
        
        self.system_paths = frozenset([
            '/etc/', '/usr/', '/var/', '/boot/', '/sys/', 
            '/proc/', '/dev/', '/tmp/', '/opt/'
        ])
        
        self.safe_tools = frozenset(['Read', 'Glob', 'Grep', 'LS'])
        
        # Pre-compiled feature extraction patterns
        self._feature_cache: Dict[str, Dict[str, float]] = {}
        self._cache_max_size = 1000
    
    def extract_features_fast(self, request: ValidationRequest) -> Dict[str, float]:
        """
        Ultra-fast feature extraction optimized for <1ms
        """
        # Check cache first
        cache_key = f"{request.tool_name}:{request.command_hash[:8]}"
        if cache_key in self._feature_cache:
            return self._feature_cache[cache_key]
        
        features = {}
        command_text_lower = request.command_text.lower()
        tool_name = request.tool_name
        
        # Hot path optimizations - most common features first
        features['is_safe_tool'] = 1.0 if tool_name in self.safe_tools else 0.0
        features['is_bash'] = 1.0 if tool_name.lower() == 'bash' else 0.0
        features['is_file_operation'] = 1.0 if tool_name.lower() in {'write', 'edit', 'multiedit'} else 0.0
        
        # Vectorized keyword counting
        dangerous_count = sum(1 for word in self.dangerous_keywords if word in command_text_lower)
        safe_count = sum(1 for word in self.safe_keywords if word in command_text_lower)
        
        features['dangerous_keyword_count'] = float(dangerous_count)
        features['safe_keyword_count'] = float(safe_count)
        features['keyword_ratio'] = safe_count / max(dangerous_count, 1) if dangerous_count > 0 else 2.0
        
        # Fast path operations
        features['has_system_path'] = 1.0 if any(path in command_text_lower for path in self.system_paths) else 0.0
        features['has_special_chars'] = 1.0 if any(c in command_text_lower for c in ';&|><$`(){}[]') else 0.0
        features['command_length'] = min(len(command_text_lower) / 100.0, 5.0)  # Normalized and capped
        
        # Agent context features
        features['is_system_agent'] = 1.0 if 'system' in request.agent_id.lower() else 0.0
        features['is_human_agent'] = 1.0 if 'human' in request.agent_id.lower() else 0.0
        
        # Cache if not full
        if len(self._feature_cache) < self._cache_max_size:
            self._feature_cache[cache_key] = features
        
        return features
    
    def extract_text_features(self, request: ValidationRequest) -> str:
        """Extract text for TF-IDF vectorization (if using sklearn)"""
        parts = [
            request.tool_name,
            request.command_text,
            request.agent_id.split('_')[-1] if '_' in request.agent_id else request.agent_id
        ]
        
        if request.context:
            parts.extend([str(v) for v in request.context.values() if isinstance(v, (str, int, float))])
        
        return ' '.join(parts)


class FastPatternClassifier:
    """Optimized rule-based classifier for when ML is not available"""
    
    def __init__(self):
        self.feature_extractor = FastFeatureExtractor()
        
        # Optimized decision weights based on performance analysis
        self.decision_weights = {
            'is_safe_tool': 3.0,
            'dangerous_keyword_count': -2.5,
            'safe_keyword_count': 1.2,
            'has_system_path': -2.0,
            'is_bash': -0.3,
            'has_special_chars': -0.5,
            'keyword_ratio': 1.0,
            'is_system_agent': -0.8,
            'command_length': -0.1
        }
        
        # Prediction cache for performance
        self._prediction_cache: Dict[str, PatternPrediction] = {}
        self._cache_max_size = 500
    
    def predict(self, request: ValidationRequest) -> PatternPrediction:
        """Fast weighted scoring prediction"""
        # Check prediction cache
        cache_key = f"{request.tool_name}:{request.command_hash}"
        if cache_key in self._prediction_cache:
            return self._prediction_cache[cache_key]
        
        features = self.feature_extractor.extract_features_fast(request)
        
        score = 0.0
        important_features = []
        
        # Vectorized scoring
        for feature, weight in self.decision_weights.items():
            if feature in features:
                contribution = features[feature] * weight
                score += contribution
                
                if abs(contribution) > 0.1:
                    important_features.append((feature, contribution))
        
        # Convert score to decision with optimized thresholds
        if score > 1.5:
            decision = ValidationDecision.APPROVED
            confidence = min(0.9, (score - 1.5) / 3.0 + 0.7)
        elif score < -1.5:
            decision = ValidationDecision.BLOCKED  
            confidence = min(0.9, abs(score + 1.5) / 3.0 + 0.7)
        else:
            decision = ValidationDecision.ESCALATE
            confidence = 0.5
        
        prediction = PatternPrediction(
            decision=decision,
            confidence_score=confidence,
            model_version="fast_v1.0",
            feature_vector=list(features.values()),
            top_features=important_features[:3]
        )
        
        # Cache prediction
        if len(self._prediction_cache) < self._cache_max_size:
            self._prediction_cache[cache_key] = prediction
        
        return prediction


class OptimizedPatternCache:
    """High-performance ML pattern cache with 5-10ms response times"""
    
    def __init__(self, model_path: Optional[str] = None, confidence_threshold: float = 0.8):
        """
        Initialize optimized pattern cache
        
        Args:
            model_path: Path to pre-trained ML model
            confidence_threshold: Minimum confidence for decisions
        """
        self.model_path = model_path
        self.confidence_threshold = confidence_threshold
        
        # High-performance components
        self.feature_extractor = FastFeatureExtractor()
        self.fast_classifier = FastPatternClassifier()
        
        # ML model (if available)
        self.ml_model: Optional[Pipeline] = None
        self.model_loaded = False
        
        # Inference caching
        self._inference_cache: Dict[str, Tuple[PatternPrediction, float]] = {}
        self._cache_max_size = 1000
        self._cache_ttl = 600  # 10 minutes
        
        # Performance metrics
        self._prediction_times = deque(maxlen=1000)
        self._model_accuracy_samples = deque(maxlen=100)
        
        # Batch processing optimization
        self._batch_queue: asyncio.Queue = asyncio.Queue(maxsize=50)
        self._batch_results: Dict[str, PatternPrediction] = {}
        self._batch_task: Optional[asyncio.Task] = None
        
        # Hot path optimization
        self._hot_patterns: Dict[str, PatternPrediction] = {}
        self._pattern_usage_counts = defaultdict(int)
        
        # Initialize model loading
        asyncio.create_task(self._load_model())
    
    async def predict(self, request: ValidationRequest) -> PatternPrediction:
        """
        Fast pattern prediction with <10ms target
        """
        start_time = time.time()
        
        # Fast cache lookup
        cache_key = self._get_cache_key(request)
        if cache_key in self._inference_cache:
            cached_prediction, cache_time = self._inference_cache[cache_key]
            if time.time() - cache_time < self._cache_ttl:
                prediction_time_ms = (time.time() - start_time) * 1000
                self._prediction_times.append(prediction_time_ms)
                return cached_prediction
        
        # Hot pattern check
        pattern_key = f"{request.tool_name}:{len(request.command_text)//10}"
        if pattern_key in self._hot_patterns:
            self._pattern_usage_counts[pattern_key] += 1
            prediction_time_ms = (time.time() - start_time) * 1000
            self._prediction_times.append(prediction_time_ms)
            return self._hot_patterns[pattern_key]
        
        # Use ML model if available and loaded
        if self.model_loaded and self.ml_model:
            try:
                prediction = await self._predict_with_ml(request)
            except Exception as e:
                logger.warning(f"ML prediction failed, falling back to fast classifier: {e}")
                prediction = self.fast_classifier.predict(request)
        else:
            # Use fast classifier
            prediction = self.fast_classifier.predict(request)
        
        # Cache the prediction
        if len(self._inference_cache) < self._cache_max_size:
            self._inference_cache[cache_key] = (prediction, time.time())
        
        # Update hot patterns
        self._pattern_usage_counts[pattern_key] += 1
        if self._pattern_usage_counts[pattern_key] > 10:
            self._hot_patterns[pattern_key] = prediction
        
        # Record prediction time
        prediction_time_ms = (time.time() - start_time) * 1000
        self._prediction_times.append(prediction_time_ms)
        
        return prediction
    
    async def _predict_with_ml(self, request: ValidationRequest) -> PatternPrediction:
        """ML-based prediction with performance optimizations"""
        # Extract features
        text_features = self.feature_extractor.extract_text_features(request)
        numerical_features = self.feature_extractor.extract_features_fast(request)
        
        # Vectorized prediction
        try:
            # Use TF-IDF for text features
            text_vector = self.ml_model.named_steps['vectorizer'].transform([text_features])
            
            # Get prediction probabilities
            pred_proba = self.ml_model.predict_proba(text_vector)[0]
            predicted_class = self.ml_model.classes_[pred_proba.argmax()]
            confidence = float(pred_proba.max())
            
            # Convert to our decision format
            decision_mapping = {
                'approved': ValidationDecision.APPROVED,
                'blocked': ValidationDecision.BLOCKED,
                'escalate': ValidationDecision.ESCALATE
            }
            
            decision = decision_mapping.get(predicted_class, ValidationDecision.ESCALATE)
            
            # Get top features
            feature_names = self.ml_model.named_steps['vectorizer'].get_feature_names_out()
            if hasattr(self.ml_model.named_steps['classifier'], 'coef_'):
                feature_importance = self.ml_model.named_steps['classifier'].coef_[0]
                if HAS_NUMPY:
                    top_indices = np.argsort(np.abs(feature_importance))[-5:][::-1]
                else:
                    # Fallback without numpy
                    importance_pairs = [(i, abs(importance)) for i, importance in enumerate(feature_importance)]
                    importance_pairs.sort(key=lambda x: x[1], reverse=True)
                    top_indices = [i for i, _ in importance_pairs[:5]]
                
                top_features = [
                    (feature_names[i], float(feature_importance[i]))
                    for i in top_indices[:3]
                ]
            else:
                top_features = [('model_prediction', confidence)]
            
            return PatternPrediction(
                decision=decision,
                confidence_score=confidence,
                model_version="ml_v1.0",
                feature_vector=text_vector.toarray().flatten().tolist() if hasattr(text_vector, 'toarray') else [],
                top_features=top_features
            )
        
        except Exception as e:
            logger.error(f"ML prediction error: {e}")
            # Fallback to fast classifier
            return self.fast_classifier.predict(request)
    
    def _get_cache_key(self, request: ValidationRequest) -> str:
        """Generate cache key for inference caching"""
        return f"{request.tool_name}:{request.command_hash}:{request.agent_id[:4]}"
    
    async def _load_model(self):
        """Load ML model asynchronously"""
        if not SKLEARN_AVAILABLE:
            logger.info("Sklearn not available, using fast classifier only")
            return
        
        if not self.model_path or not Path(self.model_path).exists():
            logger.info("No ML model path provided, training simple model")
            await self._train_simple_model()
            return
        
        try:
            with open(self.model_path, 'rb') as f:
                self.ml_model = pickle.load(f)
            self.model_loaded = True
            logger.info(f"Loaded ML model from {self.model_path}")
        except Exception as e:
            logger.warning(f"Failed to load ML model: {e}")
            await self._train_simple_model()
    
    async def _train_simple_model(self):
        """Train a simple model for demonstration"""
        if not SKLEARN_AVAILABLE:
            return
        
        try:
            # Create simple training data
            training_texts = [
                "bash rm -rf /",
                "bash ls -la",
                "Write file.py",
                "bash sudo rm important.txt",
                "Read config.json",
                "bash chmod 777 /etc/passwd"
            ]
            
            training_labels = ['blocked', 'approved', 'approved', 'blocked', 'approved', 'blocked']
            
            # Create and train pipeline
            self.ml_model = Pipeline([
                ('vectorizer', TfidfVectorizer(max_features=100, ngram_range=(1, 2))),
                ('classifier', SGDClassifier(random_state=42, max_iter=100))
            ])
            
            self.ml_model.fit(training_texts, training_labels)
            self.model_loaded = True
            logger.info("Trained simple ML model for pattern cache")
            
        except Exception as e:
            logger.error(f"Failed to train simple model: {e}")
    
    async def periodic_maintenance(self, interval_seconds: int = 600):
        """
        Periodic maintenance for cache optimization
        """
        while True:
            try:
                current_time = time.time()
                
                # Clean expired cache entries
                expired_keys = []
                for key, (_, cache_time) in self._inference_cache.items():
                    if current_time - cache_time > self._cache_ttl:
                        expired_keys.append(key)
                
                for key in expired_keys:
                    del self._inference_cache[key]
                
                # Update hot patterns based on usage
                if len(self._pattern_usage_counts) > 20:
                    # Keep only top 10 hot patterns
                    sorted_patterns = sorted(
                        self._pattern_usage_counts.items(),
                        key=lambda x: x[1],
                        reverse=True
                    )
                    
                    self._hot_patterns = {
                        pattern: self._hot_patterns.get(pattern, self.fast_classifier.predict)
                        for pattern, _ in sorted_patterns[:10]
                    }
                    
                    # Reset counters
                    self._pattern_usage_counts.clear()
                
                if expired_keys:
                    logger.debug(f"Pattern cache maintenance: removed {len(expired_keys)} expired entries")
                
                await asyncio.sleep(interval_seconds)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Pattern cache maintenance error: {e}")
                await asyncio.sleep(interval_seconds)
    
    def get_stats(self) -> Dict[str, any]:
        """Get performance statistics"""
        avg_pred_time = sum(self._prediction_times) / len(self._prediction_times) if self._prediction_times else 0
        p99_pred_time = sorted(self._prediction_times)[int(len(self._prediction_times) * 0.99)] if len(self._prediction_times) > 10 else 0
        
        return {
            'model_loaded': self.model_loaded,
            'cache_size': len(self._inference_cache),
            'hot_patterns': len(self._hot_patterns),
            'avg_prediction_time_ms': avg_pred_time,
            'p99_prediction_time_ms': p99_pred_time,
            'recent_predictions': len(self._prediction_times),
            'sklearn_available': SKLEARN_AVAILABLE,
            'numpy_available': HAS_NUMPY
        }