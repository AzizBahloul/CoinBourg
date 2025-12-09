"""
ML Predictor
============
Machine learning price prediction and feature engineering.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split, cross_val_score
import joblib
import os

logger = logging.getLogger(__name__)

# Optional imports with fallback
try:
    import xgboost as xgb
    HAS_XGBOOST = True
except ImportError:
    HAS_XGBOOST = False
    logger.warning("XGBoost not available, using Random Forest only")

try:
    from sklearn.neural_network import MLPClassifier
    HAS_NEURAL_NET = True
except ImportError:
    HAS_NEURAL_NET = False


@dataclass
class Prediction:
    """ML prediction result."""
    symbol: str
    timestamp: datetime
    predicted_direction: str  # UP, DOWN, SIDEWAYS
    predicted_price: float
    confidence: float
    horizon: str  # 1h, 4h, 1d
    features_used: int
    model_type: str


@dataclass
class ModelMetrics:
    """Model performance metrics."""
    model_name: str
    accuracy: float
    precision: float
    recall: float
    f1_score: float
    cv_score: float
    training_samples: int


class FeatureEngineer:
    """
    Feature engineering for price prediction.
    
    Features:
    - Technical indicators (RSI, MACD, Bollinger Bands)
    - Price-based (returns, volatility, momentum)
    - Volume-based (volume ratio, OBV)
    - Time-based (hour, day of week, month)
    - Market microstructure (bid-ask, order flow)
    """
    
    @staticmethod
    def create_features(data: pd.DataFrame) -> pd.DataFrame:
        """
        Create comprehensive feature set.
        
        Args:
            data: DataFrame with OHLCV data
            
        Returns:
            DataFrame with engineered features
        """
        df = data.copy()
        
        # Price-based features
        df['returns_1'] = df['close'].pct_change(1)
        df['returns_5'] = df['close'].pct_change(5)
        df['returns_10'] = df['close'].pct_change(10)
        df['returns_20'] = df['close'].pct_change(20)
        
        # Volatility
        df['volatility_5'] = df['returns_1'].rolling(5).std()
        df['volatility_10'] = df['returns_1'].rolling(10).std()
        df['volatility_20'] = df['returns_1'].rolling(20).std()
        
        # Momentum
        df['momentum_5'] = df['close'] / df['close'].shift(5) - 1
        df['momentum_10'] = df['close'] / df['close'].shift(10) - 1
        df['momentum_20'] = df['close'] / df['close'].shift(20) - 1
        
        # Moving averages
        df['sma_5'] = df['close'].rolling(5).mean()
        df['sma_10'] = df['close'].rolling(10).mean()
        df['sma_20'] = df['close'].rolling(20).mean()
        df['sma_50'] = df['close'].rolling(50).mean()
        
        # MA crossovers
        df['ma_5_20_cross'] = df['sma_5'] / df['sma_20'] - 1
        df['ma_10_50_cross'] = df['sma_10'] / df['sma_50'] - 1
        
        # EMA
        df['ema_12'] = df['close'].ewm(span=12).mean()
        df['ema_26'] = df['close'].ewm(span=26).mean()
        
        # MACD
        df['macd'] = df['ema_12'] - df['ema_26']
        df['macd_signal'] = df['macd'].ewm(span=9).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']
        
        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # Bollinger Bands
        df['bb_middle'] = df['close'].rolling(20).mean()
        bb_std = df['close'].rolling(20).std()
        df['bb_upper'] = df['bb_middle'] + 2 * bb_std
        df['bb_lower'] = df['bb_middle'] - 2 * bb_std
        df['bb_position'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])
        
        # Volume features
        df['volume_ratio'] = df['volume'] / df['volume'].rolling(20).mean()
        df['volume_trend'] = df['volume'].rolling(5).mean() / df['volume'].rolling(20).mean()
        
        # OBV (On-Balance Volume)
        df['obv'] = (np.sign(df['close'].diff()) * df['volume']).fillna(0).cumsum()
        df['obv_ema'] = df['obv'].ewm(span=20).mean()
        
        # Price range
        df['high_low_ratio'] = df['high'] / df['low']
        df['range_pct'] = (df['high'] - df['low']) / df['close']
        
        # Distance from highs/lows
        df['dist_from_high_20'] = (df['close'] - df['high'].rolling(20).max()) / df['close']
        df['dist_from_low_20'] = (df['close'] - df['low'].rolling(20).min()) / df['close']
        
        # ATR (Average True Range)
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['atr'] = true_range.rolling(14).mean()
        df['atr_pct'] = df['atr'] / df['close']
        
        # Time-based features (if timestamp available)
        if 'timestamp' in df.columns:
            df['hour'] = pd.to_datetime(df['timestamp']).dt.hour
            df['day_of_week'] = pd.to_datetime(df['timestamp']).dt.dayofweek
            df['month'] = pd.to_datetime(df['timestamp']).dt.month
        
        # Target variable (next period return)
        df['target_return'] = df['close'].shift(-1) / df['close'] - 1
        df['target_direction'] = np.where(df['target_return'] > 0.001, 1,  # UP
                                         np.where(df['target_return'] < -0.001, -1,  # DOWN
                                                 0))  # SIDEWAYS
        
        return df
    
    @staticmethod
    def select_features(df: pd.DataFrame) -> List[str]:
        """Select most relevant features."""
        feature_cols = [
            'returns_1', 'returns_5', 'returns_10', 'returns_20',
            'volatility_5', 'volatility_10', 'volatility_20',
            'momentum_5', 'momentum_10', 'momentum_20',
            'ma_5_20_cross', 'ma_10_50_cross',
            'macd', 'macd_signal', 'macd_hist',
            'rsi', 'bb_position',
            'volume_ratio', 'volume_trend',
            'high_low_ratio', 'range_pct',
            'dist_from_high_20', 'dist_from_low_20',
            'atr_pct'
        ]
        
        # Add time features if available
        if 'hour' in df.columns:
            feature_cols.extend(['hour', 'day_of_week', 'month'])
        
        # Filter to existing columns
        feature_cols = [col for col in feature_cols if col in df.columns]
        
        return feature_cols


class MLPredictor:
    """
    Machine learning price predictor.
    
    Models:
    - Random Forest (baseline, fast, interpretable)
    - XGBoost (advanced, high accuracy)
    - Ensemble (combines multiple models)
    """
    
    def __init__(
        self,
        model_dir: str = "models",
        retrain_interval_hours: int = 24
    ):
        """
        Initialize ML predictor.
        
        Args:
            model_dir: Directory to save/load models
            retrain_interval_hours: Hours between retraining
        """
        self.model_dir = model_dir
        self.retrain_interval = timedelta(hours=retrain_interval_hours)
        
        # Create model directory
        os.makedirs(model_dir, exist_ok=True)
        
        # Models
        self.models = {}
        self.scalers = {}
        self.feature_cols = []
        self.last_train_time: Optional[datetime] = None
        
        # Metrics
        self.metrics: Dict[str, ModelMetrics] = {}
        
        logger.info(f"MLPredictor initialized - Model dir: {model_dir}")
    
    async def train(
        self,
        symbol: str,
        data: pd.DataFrame,
        test_size: float = 0.2
    ) -> Dict[str, ModelMetrics]:
        """
        Train models on historical data.
        
        Args:
            symbol: Trading symbol
            data: Historical OHLCV data
            test_size: Test set proportion
            
        Returns:
            Dict of model metrics
        """
        logger.info(f"Training models for {symbol} on {len(data)} samples")
        
        # Feature engineering
        df = FeatureEngineer.create_features(data)
        self.feature_cols = FeatureEngineer.select_features(df)
        
        # Drop NaN rows
        df = df.dropna()
        
        if len(df) < 100:
            raise ValueError(f"Insufficient data after feature engineering: {len(df)} samples")
        
        # Prepare X and y
        X = df[self.feature_cols].values
        y_direction = df['target_direction'].values
        y_price = df['target_return'].values
        
        # Split data
        X_train, X_test, y_dir_train, y_dir_test, y_price_train, y_price_test = train_test_split(
            X, y_direction, y_price, test_size=test_size, shuffle=False
        )
        
        # Scale features
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)
        
        self.scalers[symbol] = scaler
        
        # Train models
        metrics = {}
        
        # 1. Random Forest Classifier (direction)
        rf_clf = RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            min_samples_split=10,
            random_state=42,
            n_jobs=-1
        )
        rf_clf.fit(X_train_scaled, y_dir_train)
        
        rf_accuracy = rf_clf.score(X_test_scaled, y_dir_test)
        rf_cv_score = np.mean(cross_val_score(rf_clf, X_train_scaled, y_dir_train, cv=5))
        
        self.models[f"{symbol}_rf_clf"] = rf_clf
        
        metrics['random_forest'] = ModelMetrics(
            model_name='Random Forest',
            accuracy=rf_accuracy,
            precision=0.0,  # Would need classification_report for this
            recall=0.0,
            f1_score=0.0,
            cv_score=rf_cv_score,
            training_samples=len(X_train)
        )
        
        logger.info(f"Random Forest: Accuracy {rf_accuracy:.3f}, CV Score {rf_cv_score:.3f}")
        
        # 2. XGBoost (if available)
        if HAS_XGBOOST:
            xgb_clf = xgb.XGBClassifier(
                n_estimators=100,
                max_depth=6,
                learning_rate=0.1,
                random_state=42,
                n_jobs=-1
            )
            xgb_clf.fit(X_train_scaled, y_dir_train)
            
            xgb_accuracy = xgb_clf.score(X_test_scaled, y_dir_test)
            xgb_cv_score = np.mean(cross_val_score(xgb_clf, X_train_scaled, y_dir_train, cv=5))
            
            self.models[f"{symbol}_xgb_clf"] = xgb_clf
            
            metrics['xgboost'] = ModelMetrics(
                model_name='XGBoost',
                accuracy=xgb_accuracy,
                precision=0.0,
                recall=0.0,
                f1_score=0.0,
                cv_score=xgb_cv_score,
                training_samples=len(X_train)
            )
            
            logger.info(f"XGBoost: Accuracy {xgb_accuracy:.3f}, CV Score {xgb_cv_score:.3f}")
        
        # 3. Random Forest Regressor (price prediction)
        rf_reg = RandomForestRegressor(
            n_estimators=100,
            max_depth=10,
            min_samples_split=10,
            random_state=42,
            n_jobs=-1
        )
        rf_reg.fit(X_train_scaled, y_price_train)
        
        self.models[f"{symbol}_rf_reg"] = rf_reg
        
        # Save models
        self._save_models(symbol)
        
        self.last_train_time = datetime.now()
        self.metrics = metrics
        
        logger.info(f"Training complete - {len(metrics)} models trained")
        
        return metrics
    
    async def predict(
        self,
        symbol: str,
        data: pd.DataFrame,
        horizon: str = "1h"
    ) -> Prediction:
        """
        Make prediction for next period.
        
        Args:
            symbol: Trading symbol
            data: Recent OHLCV data (last 100+ bars)
            horizon: Prediction horizon (1h, 4h, 1d)
            
        Returns:
            Prediction with direction and price
        """
        # Check if retraining needed
        if self.last_train_time is None or \
           datetime.now() - self.last_train_time > self.retrain_interval:
            logger.info("Retraining models...")
            await self.train(symbol, data)
        
        # Load models if not in memory
        if f"{symbol}_rf_clf" not in self.models:
            self._load_models(symbol)
        
        # Feature engineering
        df = FeatureEngineer.create_features(data)
        
        # Get last row features
        if len(df) < 1:
            raise ValueError("Insufficient data for prediction")
        
        last_row = df.iloc[-1]
        X = last_row[self.feature_cols].values.reshape(1, -1)
        
        # Scale
        if symbol not in self.scalers:
            raise ValueError(f"Scaler not found for {symbol}. Train models first.")
        
        X_scaled = self.scalers[symbol].transform(X)
        
        # Predict with ensemble
        predictions = []
        confidences = []
        
        # Random Forest
        if f"{symbol}_rf_clf" in self.models:
            rf_pred = self.models[f"{symbol}_rf_clf"].predict(X_scaled)[0]
            rf_proba = self.models[f"{symbol}_rf_clf"].predict_proba(X_scaled)[0]
            predictions.append(rf_pred)
            confidences.append(rf_proba.max())
        
        # XGBoost
        if f"{symbol}_xgb_clf" in self.models:
            xgb_pred = self.models[f"{symbol}_xgb_clf"].predict(X_scaled)[0]
            xgb_proba = self.models[f"{symbol}_xgb_clf"].predict_proba(X_scaled)[0]
            predictions.append(xgb_pred)
            confidences.append(xgb_proba.max())
        
        # Ensemble: majority vote
        if predictions:
            pred_direction_value = np.mean(predictions)
            avg_confidence = np.mean(confidences)
            
            if pred_direction_value > 0.5:
                pred_direction = "UP"
            elif pred_direction_value < -0.5:
                pred_direction = "DOWN"
            else:
                pred_direction = "SIDEWAYS"
        else:
            pred_direction = "SIDEWAYS"
            avg_confidence = 0.0
        
        # Price prediction
        if f"{symbol}_rf_reg" in self.models:
            pred_return = self.models[f"{symbol}_rf_reg"].predict(X_scaled)[0]
            current_price = data['close'].iloc[-1]
            pred_price = current_price * (1 + pred_return)
        else:
            pred_price = data['close'].iloc[-1]
        
        prediction = Prediction(
            symbol=symbol,
            timestamp=datetime.now(),
            predicted_direction=pred_direction,
            predicted_price=pred_price,
            confidence=avg_confidence,
            horizon=horizon,
            features_used=len(self.feature_cols),
            model_type="Ensemble (RF+XGB)" if HAS_XGBOOST else "Random Forest"
        )
        
        logger.info(f"Prediction for {symbol}: {pred_direction} @ ${pred_price:.2f} "
                   f"(confidence: {avg_confidence:.2f})")
        
        return prediction
    
    def get_feature_importance(
        self,
        symbol: str,
        top_n: int = 10
    ) -> List[Tuple[str, float]]:
        """
        Get feature importance from Random Forest.
        
        Args:
            symbol: Trading symbol
            top_n: Number of top features
            
        Returns:
            List of (feature_name, importance) tuples
        """
        model_key = f"{symbol}_rf_clf"
        
        if model_key not in self.models:
            logger.warning(f"Model not found for {symbol}")
            return []
        
        importances = self.models[model_key].feature_importances_
        
        feature_importance = list(zip(self.feature_cols, importances))
        feature_importance.sort(key=lambda x: x[1], reverse=True)
        
        return feature_importance[:top_n]
    
    def _save_models(self, symbol: str):
        """Save models to disk."""
        for model_name, model in self.models.items():
            if symbol in model_name:
                filepath = os.path.join(self.model_dir, f"{model_name}.pkl")
                joblib.dump(model, filepath)
        
        # Save scaler
        if symbol in self.scalers:
            scaler_path = os.path.join(self.model_dir, f"{symbol}_scaler.pkl")
            joblib.dump(self.scalers[symbol], scaler_path)
        
        logger.info(f"Models saved for {symbol}")
    
    def _load_models(self, symbol: str):
        """Load models from disk."""
        # Load classifier
        rf_clf_path = os.path.join(self.model_dir, f"{symbol}_rf_clf.pkl")
        if os.path.exists(rf_clf_path):
            self.models[f"{symbol}_rf_clf"] = joblib.load(rf_clf_path)
        
        # Load XGBoost if exists
        if HAS_XGBOOST:
            xgb_clf_path = os.path.join(self.model_dir, f"{symbol}_xgb_clf.pkl")
            if os.path.exists(xgb_clf_path):
                self.models[f"{symbol}_xgb_clf"] = joblib.load(xgb_clf_path)
        
        # Load regressor
        rf_reg_path = os.path.join(self.model_dir, f"{symbol}_rf_reg.pkl")
        if os.path.exists(rf_reg_path):
            self.models[f"{symbol}_rf_reg"] = joblib.load(rf_reg_path)
        
        # Load scaler
        scaler_path = os.path.join(self.model_dir, f"{symbol}_scaler.pkl")
        if os.path.exists(scaler_path):
            self.scalers[symbol] = joblib.load(scaler_path)
        
        logger.info(f"Models loaded for {symbol}")
