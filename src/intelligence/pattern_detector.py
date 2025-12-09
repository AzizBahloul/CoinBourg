"""
Pattern Detector
================
Chart pattern recognition for technical analysis.
"""

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import numpy as np
from scipy.signal import find_peaks, argrelextrema
import pandas as pd

logger = logging.getLogger(__name__)


class PatternType(Enum):
    """Chart pattern types."""
    # Reversal patterns
    HEAD_AND_SHOULDERS = "head_and_shoulders"
    INVERSE_HEAD_AND_SHOULDERS = "inverse_head_and_shoulders"
    DOUBLE_TOP = "double_top"
    DOUBLE_BOTTOM = "double_bottom"
    TRIPLE_TOP = "triple_top"
    TRIPLE_BOTTOM = "triple_bottom"
    
    # Continuation patterns
    ASCENDING_TRIANGLE = "ascending_triangle"
    DESCENDING_TRIANGLE = "descending_triangle"
    SYMMETRICAL_TRIANGLE = "symmetrical_triangle"
    FLAG = "flag"
    PENNANT = "pennant"
    WEDGE_RISING = "wedge_rising"
    WEDGE_FALLING = "wedge_falling"
    
    # Candlestick patterns
    DOJI = "doji"
    HAMMER = "hammer"
    SHOOTING_STAR = "shooting_star"
    ENGULFING_BULLISH = "engulfing_bullish"
    ENGULFING_BEARISH = "engulfing_bearish"
    MORNING_STAR = "morning_star"
    EVENING_STAR = "evening_star"


@dataclass
class Pattern:
    """Detected chart pattern."""
    pattern_type: PatternType
    start_idx: int
    end_idx: int
    confidence: float
    direction: str  # BULLISH, BEARISH, NEUTRAL
    target_price: Optional[float]
    stop_loss: Optional[float]
    description: str


class PatternDetector:
    """
    Chart pattern recognition engine.
    
    Detects:
    - Classic chart patterns (head & shoulders, triangles, flags)
    - Candlestick patterns (doji, hammers, engulfing)
    - Support/resistance levels
    - Trend lines
    """
    
    def __init__(
        self,
        min_pattern_length: int = 20,
        max_pattern_length: int = 100,
        confidence_threshold: float = 0.6
    ):
        """
        Initialize pattern detector.
        
        Args:
            min_pattern_length: Minimum bars for pattern
            max_pattern_length: Maximum bars for pattern
            confidence_threshold: Minimum confidence to report
        """
        self.min_pattern_length = min_pattern_length
        self.max_pattern_length = max_pattern_length
        self.confidence_threshold = confidence_threshold
        
        logger.info("PatternDetector initialized")
    
    def detect_patterns(
        self,
        ohlc_data: pd.DataFrame
    ) -> List[Pattern]:
        """
        Detect all patterns in OHLC data.
        
        Args:
            ohlc_data: DataFrame with columns: open, high, low, close, volume
            
        Returns:
            List of detected patterns
        """
        logger.info(f"Detecting patterns in {len(ohlc_data)} bars")
        
        patterns = []
        
        # Detect chart patterns
        patterns.extend(self._detect_head_and_shoulders(ohlc_data))
        patterns.extend(self._detect_double_tops_bottoms(ohlc_data))
        patterns.extend(self._detect_triangles(ohlc_data))
        patterns.extend(self._detect_flags_pennants(ohlc_data))
        
        # Detect candlestick patterns (last 50 bars for recent signals)
        recent_data = ohlc_data.iloc[-50:]
        patterns.extend(self._detect_candlestick_patterns(recent_data))
        
        # Filter by confidence
        patterns = [p for p in patterns if p.confidence >= self.confidence_threshold]
        
        # Sort by confidence
        patterns.sort(key=lambda x: x.confidence, reverse=True)
        
        logger.info(f"Detected {len(patterns)} patterns above {self.confidence_threshold} confidence")
        
        return patterns
    
    def _detect_head_and_shoulders(self, data: pd.DataFrame) -> List[Pattern]:
        """Detect head and shoulders patterns."""
        patterns = []
        high = data['high'].values
        low = data['low'].values
        close = data['close'].values
        
        # Find peaks and troughs
        peaks, _ = find_peaks(high, distance=self.min_pattern_length // 3)
        troughs, _ = find_peaks(-low, distance=self.min_pattern_length // 3)
        
        # Need at least 3 peaks for H&S
        if len(peaks) < 3:
            return patterns
        
        # Check consecutive peaks for H&S pattern
        for i in range(len(peaks) - 2):
            left_shoulder = peaks[i]
            head = peaks[i + 1]
            right_shoulder = peaks[i + 2]
            
            # H&S criteria:
            # 1. Head higher than shoulders
            # 2. Shoulders at similar height
            if (high[head] > high[left_shoulder] and 
                high[head] > high[right_shoulder]):
                
                shoulder_diff = abs(high[left_shoulder] - high[right_shoulder])
                shoulder_avg = (high[left_shoulder] + high[right_shoulder]) / 2
                
                # Shoulders should be similar (within 3%)
                if shoulder_diff / shoulder_avg < 0.03:
                    # Find neckline (troughs between peaks)
                    neckline_troughs = [t for t in troughs if left_shoulder < t < right_shoulder]
                    
                    if len(neckline_troughs) >= 2:
                        neckline_level = np.mean([low[t] for t in neckline_troughs])
                        
                        # Target: distance from head to neckline
                        target = neckline_level - (high[head] - neckline_level)
                        
                        confidence = 0.7
                        if right_shoulder < len(close) - 5:  # Not too recent
                            confidence = 0.8
                        
                        patterns.append(Pattern(
                            pattern_type=PatternType.HEAD_AND_SHOULDERS,
                            start_idx=left_shoulder,
                            end_idx=right_shoulder,
                            confidence=confidence,
                            direction="BEARISH",
                            target_price=target,
                            stop_loss=high[head],
                            description=f"Head & Shoulders (neckline: {neckline_level:.2f})"
                        ))
        
        # Inverse H&S (same logic but inverted)
        for i in range(len(troughs) - 2):
            left_shoulder = troughs[i]
            head = troughs[i + 1]
            right_shoulder = troughs[i + 2]
            
            if (low[head] < low[left_shoulder] and 
                low[head] < low[right_shoulder]):
                
                shoulder_diff = abs(low[left_shoulder] - low[right_shoulder])
                shoulder_avg = (low[left_shoulder] + low[right_shoulder]) / 2
                
                if shoulder_diff / shoulder_avg < 0.03:
                    neckline_peaks = [p for p in peaks if left_shoulder < p < right_shoulder]
                    
                    if len(neckline_peaks) >= 2:
                        neckline_level = np.mean([high[p] for p in neckline_peaks])
                        target = neckline_level + (neckline_level - low[head])
                        
                        confidence = 0.7
                        if right_shoulder < len(close) - 5:
                            confidence = 0.8
                        
                        patterns.append(Pattern(
                            pattern_type=PatternType.INVERSE_HEAD_AND_SHOULDERS,
                            start_idx=left_shoulder,
                            end_idx=right_shoulder,
                            confidence=confidence,
                            direction="BULLISH",
                            target_price=target,
                            stop_loss=low[head],
                            description=f"Inverse H&S (neckline: {neckline_level:.2f})"
                        ))
        
        return patterns
    
    def _detect_double_tops_bottoms(self, data: pd.DataFrame) -> List[Pattern]:
        """Detect double top and double bottom patterns."""
        patterns = []
        high = data['high'].values
        low = data['low'].values
        
        # Find peaks and troughs
        peaks, _ = find_peaks(high, distance=self.min_pattern_length // 2)
        troughs, _ = find_peaks(-low, distance=self.min_pattern_length // 2)
        
        # Double top
        for i in range(len(peaks) - 1):
            first_peak = peaks[i]
            second_peak = peaks[i + 1]
            
            # Peaks should be at similar level (within 2%)
            peak_diff = abs(high[first_peak] - high[second_peak])
            peak_avg = (high[first_peak] + high[second_peak]) / 2
            
            if peak_diff / peak_avg < 0.02:
                # Find trough between peaks
                between_troughs = [t for t in troughs if first_peak < t < second_peak]
                
                if between_troughs:
                    valley = between_troughs[0]
                    valley_level = low[valley]
                    
                    # Target: distance from peaks to valley
                    target = valley_level - (peak_avg - valley_level)
                    
                    patterns.append(Pattern(
                        pattern_type=PatternType.DOUBLE_TOP,
                        start_idx=first_peak,
                        end_idx=second_peak,
                        confidence=0.75,
                        direction="BEARISH",
                        target_price=target,
                        stop_loss=peak_avg * 1.02,
                        description=f"Double Top at {peak_avg:.2f}"
                    ))
        
        # Double bottom
        for i in range(len(troughs) - 1):
            first_trough = troughs[i]
            second_trough = troughs[i + 1]
            
            trough_diff = abs(low[first_trough] - low[second_trough])
            trough_avg = (low[first_trough] + low[second_trough]) / 2
            
            if trough_diff / trough_avg < 0.02:
                between_peaks = [p for p in peaks if first_trough < p < second_trough]
                
                if between_peaks:
                    peak = between_peaks[0]
                    peak_level = high[peak]
                    
                    target = peak_level + (peak_level - trough_avg)
                    
                    patterns.append(Pattern(
                        pattern_type=PatternType.DOUBLE_BOTTOM,
                        start_idx=first_trough,
                        end_idx=second_trough,
                        confidence=0.75,
                        direction="BULLISH",
                        target_price=target,
                        stop_loss=trough_avg * 0.98,
                        description=f"Double Bottom at {trough_avg:.2f}"
                    ))
        
        return patterns
    
    def _detect_triangles(self, data: pd.DataFrame) -> List[Pattern]:
        """Detect triangle patterns."""
        patterns = []
        high = data['high'].values
        low = data['low'].values
        
        window = min(self.max_pattern_length, len(data) // 2)
        
        for start in range(len(data) - window):
            end = start + window
            window_data = data.iloc[start:end]
            
            # Fit trend lines to highs and lows
            highs = window_data['high'].values
            lows = window_data['low'].values
            x = np.arange(len(highs))
            
            # Upper trend line
            upper_slope, upper_intercept = np.polyfit(x, highs, 1)
            
            # Lower trend line
            lower_slope, lower_intercept = np.polyfit(x, lows, 1)
            
            # Ascending triangle: flat top, rising bottom
            if abs(upper_slope) < 0.0001 and lower_slope > 0.0001:
                resistance = np.mean(highs[-10:])  # Last 10 highs
                
                patterns.append(Pattern(
                    pattern_type=PatternType.ASCENDING_TRIANGLE,
                    start_idx=start,
                    end_idx=end,
                    confidence=0.65,
                    direction="BULLISH",
                    target_price=resistance * 1.05,
                    stop_loss=lows[-1] * 0.98,
                    description="Ascending Triangle"
                ))
            
            # Descending triangle: declining top, flat bottom
            elif upper_slope < -0.0001 and abs(lower_slope) < 0.0001:
                support = np.mean(lows[-10:])
                
                patterns.append(Pattern(
                    pattern_type=PatternType.DESCENDING_TRIANGLE,
                    start_idx=start,
                    end_idx=end,
                    confidence=0.65,
                    direction="BEARISH",
                    target_price=support * 0.95,
                    stop_loss=highs[-1] * 1.02,
                    description="Descending Triangle"
                ))
            
            # Symmetrical triangle: converging lines
            elif upper_slope < -0.0001 and lower_slope > 0.0001:
                current_price = data['close'].iloc[end - 1]
                
                patterns.append(Pattern(
                    pattern_type=PatternType.SYMMETRICAL_TRIANGLE,
                    start_idx=start,
                    end_idx=end,
                    confidence=0.60,
                    direction="NEUTRAL",
                    target_price=None,
                    stop_loss=None,
                    description="Symmetrical Triangle (breakout pending)"
                ))
        
        return patterns
    
    def _detect_flags_pennants(self, data: pd.DataFrame) -> List[Pattern]:
        """Detect flag and pennant patterns."""
        patterns = []
        close = data['close'].values
        volume = data['volume'].values
        
        # Flags: sharp move + consolidation
        for i in range(50, len(data) - 20):
            # Check for sharp move (flagpole)
            pole_start = i - 20
            pole_end = i
            pole_move = (close[pole_end] - close[pole_start]) / close[pole_start]
            
            # Need >5% move
            if abs(pole_move) < 0.05:
                continue
            
            # Check for consolidation (flag)
            flag_end = min(i + 20, len(data))
            flag_data = close[pole_end:flag_end]
            
            if len(flag_data) < 10:
                continue
            
            # Low volatility in flag
            flag_volatility = np.std(flag_data) / np.mean(flag_data)
            
            if flag_volatility < 0.02:  # Low volatility
                direction = "BULLISH" if pole_move > 0 else "BEARISH"
                
                # Target: flagpole height projected from breakout
                target = close[flag_end - 1] + (close[pole_end] - close[pole_start])
                
                patterns.append(Pattern(
                    pattern_type=PatternType.FLAG,
                    start_idx=pole_start,
                    end_idx=flag_end,
                    confidence=0.70,
                    direction=direction,
                    target_price=target,
                    stop_loss=close[pole_start],
                    description=f"{'Bull' if direction == 'BULLISH' else 'Bear'} Flag"
                ))
        
        return patterns
    
    def _detect_candlestick_patterns(self, data: pd.DataFrame) -> List[Pattern]:
        """Detect candlestick patterns."""
        patterns = []
        
        for i in range(1, len(data)):
            row = data.iloc[i]
            prev_row = data.iloc[i - 1]
            
            open_price = row['open']
            high = row['high']
            low = row['low']
            close = row['close']
            
            body = abs(close - open_price)
            total_range = high - low
            upper_wick = high - max(open_price, close)
            lower_wick = min(open_price, close) - low
            
            # Doji: small body (<1% of range)
            if body / total_range < 0.01:
                patterns.append(Pattern(
                    pattern_type=PatternType.DOJI,
                    start_idx=i,
                    end_idx=i,
                    confidence=0.65,
                    direction="NEUTRAL",
                    target_price=None,
                    stop_loss=None,
                    description="Doji (indecision)"
                ))
            
            # Hammer: long lower wick, small body at top
            if (lower_wick > body * 2 and 
                upper_wick < body * 0.5 and
                close < open_price):
                
                patterns.append(Pattern(
                    pattern_type=PatternType.HAMMER,
                    start_idx=i,
                    end_idx=i,
                    confidence=0.70,
                    direction="BULLISH",
                    target_price=close * 1.03,
                    stop_loss=low * 0.99,
                    description="Hammer (bullish reversal)"
                ))
            
            # Shooting Star: long upper wick, small body at bottom
            if (upper_wick > body * 2 and 
                lower_wick < body * 0.5 and
                close > open_price):
                
                patterns.append(Pattern(
                    pattern_type=PatternType.SHOOTING_STAR,
                    start_idx=i,
                    end_idx=i,
                    confidence=0.70,
                    direction="BEARISH",
                    target_price=close * 0.97,
                    stop_loss=high * 1.01,
                    description="Shooting Star (bearish reversal)"
                ))
            
            # Engulfing patterns
            prev_body = abs(prev_row['close'] - prev_row['open'])
            
            # Bullish engulfing
            if (prev_row['close'] < prev_row['open'] and  # Prev bearish
                close > open_price and  # Current bullish
                body > prev_body * 1.2):  # Engulfs previous
                
                patterns.append(Pattern(
                    pattern_type=PatternType.ENGULFING_BULLISH,
                    start_idx=i - 1,
                    end_idx=i,
                    confidence=0.75,
                    direction="BULLISH",
                    target_price=close * 1.05,
                    stop_loss=low * 0.98,
                    description="Bullish Engulfing"
                ))
            
            # Bearish engulfing
            if (prev_row['close'] > prev_row['open'] and  # Prev bullish
                close < open_price and  # Current bearish
                body > prev_body * 1.2):
                
                patterns.append(Pattern(
                    pattern_type=PatternType.ENGULFING_BEARISH,
                    start_idx=i - 1,
                    end_idx=i,
                    confidence=0.75,
                    direction="BEARISH",
                    target_price=close * 0.95,
                    stop_loss=high * 1.02,
                    description="Bearish Engulfing"
                ))
        
        return patterns
    
    def find_support_resistance(
        self,
        data: pd.DataFrame,
        n_levels: int = 5
    ) -> Dict[str, List[float]]:
        """
        Find support and resistance levels.
        
        Args:
            data: OHLC data
            n_levels: Number of levels to find
            
        Returns:
            Dict with 'support' and 'resistance' lists
        """
        high = data['high'].values
        low = data['low'].values
        
        # Find peaks (resistance) and troughs (support)
        peaks, _ = find_peaks(high, distance=10)
        troughs, _ = find_peaks(-low, distance=10)
        
        # Cluster nearby levels
        resistance_levels = self._cluster_levels(high[peaks], n_levels)
        support_levels = self._cluster_levels(low[troughs], n_levels)
        
        logger.info(f"Found {len(resistance_levels)} resistance and {len(support_levels)} support levels")
        
        return {
            'resistance': resistance_levels,
            'support': support_levels
        }
    
    def _cluster_levels(self, levels: np.ndarray, n_clusters: int) -> List[float]:
        """Cluster price levels."""
        if len(levels) == 0:
            return []
        
        # Simple clustering: bin levels and take most frequent
        levels = sorted(levels)
        clusters = []
        
        i = 0
        while i < len(levels) and len(clusters) < n_clusters:
            cluster = [levels[i]]
            j = i + 1
            
            # Group nearby levels (within 1%)
            while j < len(levels) and (levels[j] - levels[i]) / levels[i] < 0.01:
                cluster.append(levels[j])
                j += 1
            
            clusters.append(np.mean(cluster))
            i = j
        
        return clusters[:n_clusters]
