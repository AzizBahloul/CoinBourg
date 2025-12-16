"""
Enhanced ML Predictor with LSTM & Online Learning
==================================================
Advanced machine learning models for price prediction with continuous improvement.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import numpy as np
import pandas as pd
import os
import joblib

logger = logging.getLogger(__name__)

# Optional TensorFlow/Keras imports
try:
    import tensorflow as tf
    from tensorflow import keras
    from tensorflow.keras.models import Sequential, load_model
    from tensorflow.keras.layers import LSTM, Dense, Dropout, Bidirectional
    from tensorflow.keras.callbacks import EarlyStopping, ModelCheckpoint
    HAS_TENSORFLOW = True
except ImportError:
    HAS_TENSORFLOW = False
    logger.warning("TensorFlow not installed - LSTM models disabled")

# Traditional ML imports
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split

try:
    import xgboost as xgb
    HAS_XGBOOST = True
except ImportError:
    HAS_XGBOOST = False


@dataclass
class Prediction:
    """ML prediction result."""
    symbol: str
    timestamp: datetime
    predicted_direction: str  # UP, DOWN, SIDEWAYS
    predicted_price: float
    predicted_change_pct: float
    confidence: float
    horizon: str  # 1h, 4h, 1d
    features_used: int
    model_type: str
    probability_up: float
    probability_down: float


class LSTMPredictor:
    """
    LSTM-based price prediction model.
    
    Features:
    - Bidirectional LSTM for better context
    - Dropout for regularization
    - Multi-horizon predictions
    - Online learning capability
    """
    
    def __init__(self, sequence_length: int = 60, features_dim: int = 10):
        """
        Initialize LSTM predictor.
        
        Args:
            sequence_length: Number of time steps to look back
            features_dim: Number of features per time step
        """
        self.sequence_length = sequence_length
        self.features_dim = features_dim
        self.model = None
        self.scaler = StandardScaler()
        self.is_trained = False
    
    def build_model(self) -> keras.Model:
        """Build LSTM model architecture."""
        if not HAS_TENSORFLOW:
            raise ImportError("TensorFlow required for LSTM models")
        
        model = Sequential([
            # First LSTM layer
            Bidirectional(
                LSTM(64, return_sequences=True, input_shape=(self.sequence_length, self.features_dim)),
                name='bidirectional_lstm_1'
            ),
            Dropout(0.2),
            
            # Second LSTM layer
            Bidirectional(LSTM(32, return_sequences=False), name='bidirectional_lstm_2'),
            Dropout(0.2),
            
            # Dense layers
            Dense(16, activation='relu'),
            Dropout(0.1),
            
            # Output layer - predict price change percentage
            Dense(3, activation='softmax', name='output')  # UP, DOWN, NEUTRAL
        ])
        
        model.compile(
            optimizer=keras.optimizers.Adam(learning_rate=0.001),
            loss='categorical_crossentropy',
            metrics=['accuracy', 'AUC']
        )
        
        return model
    
    async def train(
        self,
        price_data: pd.DataFrame,
        target_col: str = 'future_return',
        epochs: int = 50,
        batch_size: int = 32
    ) -> Dict:
        """
        Train LSTM model.
        
        Args:
            price_data: DataFrame with OHLCV and features
            target_col: Column name for target variable
            epochs: Training epochs
            batch_size: Batch size
            
        Returns:
            Training metrics
        """
        if not HAS_TENSORFLOW:
            return {'error': 'TensorFlow not available'}
        
        # Prepare sequences
        X, y = self._prepare_sequences(price_data, target_col)
        
        if len(X) < 100:
            logger.warning(f"Insufficient data for training: {len(X)} samples")
            return {'error': 'Insufficient data'}
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, shuffle=False  # Don't shuffle time series
        )
        
        # Build model if not exists
        if self.model is None:
            self.model = self.build_model()
        
        # Callbacks
        early_stop = EarlyStopping(
            monitor='val_loss',
            patience=10,
            restore_best_weights=True
        )
        
        # Train
        history = self.model.fit(
            X_train, y_train,
            validation_data=(X_test, y_test),
            epochs=epochs,
            batch_size=batch_size,
            callbacks=[early_stop],
            verbose=0
        )
        
        # Evaluate
        test_loss, test_accuracy, test_auc = self.model.evaluate(X_test, y_test, verbose=0)
        
        self.is_trained = True
        
        logger.info(f"LSTM trained: accuracy={test_accuracy:.3f}, AUC={test_auc:.3f}")
        
        return {
            'test_accuracy': float(test_accuracy),
            'test_auc': float(test_auc),
            'test_loss': float(test_loss),
            'epochs_trained': len(history.history['loss']),
            'samples_trained': len(X_train)
        }
    
    def _prepare_sequences(
        self,
        data: pd.DataFrame,
        target_col: str
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Prepare sequential data for LSTM."""
        
        # Select feature columns (exclude target and non-numeric)
        feature_cols = [col for col in data.columns if col != target_col and data[col].dtype in [np.float64, np.int64]]
        
        # Scale features
        scaled_data = self.scaler.fit_transform(data[feature_cols].values)
        
        # Create sequences
        X, y = [], []
        
        for i in range(len(scaled_data) - self.sequence_length):
            X.append(scaled_data[i:i + self.sequence_length])
            
            # Target: classify as UP (0), DOWN (1), or NEUTRAL (2)
            future_return = data[target_col].iloc[i + self.sequence_length]
            if future_return > 0.5:  # >0.5% up
                y.append([1, 0, 0])
            elif future_return < -0.5:  # <-0.5% down
                y.append([0, 1, 0])
            else:
                y.append([0, 0, 1])
        
        return np.array(X), np.array(y)
    
    async def predict(self, recent_data: pd.DataFrame) -> Optional[Prediction]:
        """Make prediction using trained model."""
        if not self.is_trained or self.model is None:
            logger.warning("LSTM model not trained")
            return None
        
        # Prepare input sequence
        feature_cols = [col for col in recent_data.columns if recent_data[col].dtype in [np.float64, np.int64]]
        scaled_data = self.scaler.transform(recent_data[feature_cols].values)
        
        if len(scaled_data) < self.sequence_length:
            logger.warning(f"Insufficient data for prediction: {len(scaled_data)} < {self.sequence_length}")
            return None
        
        # Take last sequence
        X = scaled_data[-self.sequence_length:].reshape(1, self.sequence_length, -1)
        
        # Predict
        probabilities = self.model.predict(X, verbose=0)[0]
        
        prob_up, prob_down, prob_neutral = probabilities
        
        # Determine direction
        if prob_up > max(prob_down, prob_neutral):
            direction = 'UP'
            confidence = prob_up
        elif prob_down > max(prob_up, prob_neutral):
            direction = 'DOWN'
            confidence = prob_down
        else:
            direction = 'SIDEWAYS'
            confidence = prob_neutral
        
        # Estimate price change
        if direction == 'UP':
            predicted_change = prob_up * 2  # Scale to percentage
        elif direction == 'DOWN':
            predicted_change = -prob_down * 2
        else:
            predicted_change = 0.0
        
        current_price = recent_data['close'].iloc[-1] if 'close' in recent_data.columns else 0.0
        predicted_price = current_price * (1 + predicted_change / 100)
        
        return Prediction(
            symbol='',  # Will be set by caller
            timestamp=datetime.utcnow(),
            predicted_direction=direction,
            predicted_price=predicted_price,
            predicted_change_pct=predicted_change,
            confidence=float(confidence),
            horizon='1h',
            features_used=len(feature_cols),
            model_type='LSTM',
            probability_up=float(prob_up),
            probability_down=float(prob_down)
        )
    
    async def update_online(self, new_data: pd.DataFrame, target_col: str):
        """
        Online learning - update model with new data.
        
        Args:
            new_data: New price data
            target_col: Target column name
        """
        if not self.is_trained or self.model is None:
            logger.warning("Cannot update untrained model online")
            return
        
        # Prepare new sequences
        X, y = self._prepare_sequences(new_data, target_col)
        
        if len(X) == 0:
            return
        
        # Partial fit with small number of epochs
        self.model.fit(X, y, epochs=1, batch_size=16, verbose=0)
        
        logger.debug(f"Online update: {len(X)} new samples")
    
    def save(self, filepath: str):
        """Save model to disk."""
        if self.model:
            self.model.save(filepath)
            joblib.dump(self.scaler, filepath + '.scaler')
            logger.info(f"LSTM model saved to {filepath}")
    
    def load(self, filepath: str):
        """Load model from disk."""
        if os.path.exists(filepath) and HAS_TENSORFLOW:
            self.model = load_model(filepath)
            self.scaler = joblib.load(filepath + '.scaler')
            self.is_trained = True
            logger.info(f"LSTM model loaded from {filepath}")


class OnlineLearningPredictor:
    """
    Online learning predictor that continuously improves from trading results.
    
    Uses incremental learning algorithms that can update without full retraining.
    """
    
    def __init__(self):
        """Initialize online learning predictor."""
        self.model = None
        self.scaler = StandardScaler()
        self.trade_results = []
        self.model_accuracy = 0.5
        
        # Use Gradient Boosting for online learning capability
        if HAS_XGBOOST:
            self.model = xgb.XGBClassifier(
                n_estimators=100,
                learning_rate=0.1,
                max_depth=5
            )
        else:
            self.model = GradientBoostingClassifier(
                n_estimators=100,
                learning_rate=0.1,
                max_depth=5
            )
    
    async def learn_from_trade(
        self,
        features: Dict,
        actual_outcome: str,  # 'WIN' or 'LOSS'
        profit_pct: float
    ):
        """
        Learn from a completed trade.
        
        Args:
            features: Feature dict used for prediction
            actual_outcome: Actual trade outcome
            profit_pct: Profit/loss percentage
        """
        # Store result
        self.trade_results.append({
            'features': features,
            'outcome': actual_outcome,
            'profit_pct': profit_pct,
            'timestamp': datetime.utcnow()
        })
        
        # Update every 10 trades
        if len(self.trade_results) % 10 == 0:
            await self._retrain_incremental()
    
    async def _retrain_incremental(self):
        """Incrementally retrain model with recent results."""
        if len(self.trade_results) < 20:
            return
        
        # Use last 100 trades
        recent_results = self.trade_results[-100:]
        
        # Prepare training data
        X = []
        y = []
        
        for result in recent_results:
            features_array = list(result['features'].values())
            X.append(features_array)
            y.append(1 if result['outcome'] == 'WIN' else 0)
        
        X = np.array(X)
        y = np.array(y)
        
        # Scale
        X_scaled = self.scaler.fit_transform(X)
        
        # Train
        if HAS_XGBOOST:
            self.model.fit(X_scaled, y, xgb_model=self.model.get_booster())
        else:
            self.model.fit(X_scaled, y)
        
        # Calculate accuracy
        predictions = self.model.predict(X_scaled)
        self.model_accuracy = np.mean(predictions == y)
        
        logger.info(f"Online learning update: {len(recent_results)} samples, accuracy={self.model_accuracy:.3f}")
    
    async def predict_trade_success(self, features: Dict) -> float:
        """
        Predict probability of trade success.
        
        Returns:
            Probability (0-1) that trade will be profitable
        """
        if len(self.trade_results) < 20:
            return 0.5  # No data yet
        
        features_array = np.array(list(features.values())).reshape(1, -1)
        features_scaled = self.scaler.transform(features_array)
        
        if hasattr(self.model, 'predict_proba'):
            prob = self.model.predict_proba(features_scaled)[0][1]
        else:
            prob = self.model.predict(features_scaled)[0]
        
        return float(prob)
    
    def get_model_accuracy(self) -> float:
        """Get current model accuracy."""
        return self.model_accuracy


# Make these available for import
__all__ = ['LSTMPredictor', 'OnlineLearningPredictor', 'Prediction']
