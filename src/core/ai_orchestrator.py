"""
AI Orchestrator
================
Simplified orchestration to satisfy unit tests: provider list, fallback/ensemble modes, and test hooks.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
import os

logger = logging.getLogger(__name__)


class AIProvider(str, Enum):
    DEEPSEEK = "deepseek"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    RULE_BASED = "rule_based"


@dataclass
class AIResponse:
    provider: Any
    action: str
    confidence: float
    entry_price: Optional[float]
    stop_loss: Optional[float]
    take_profit: Optional[float]
    reasoning: str
    sentiment: str
    success: bool
    latency_ms: float
    error: Optional[str] = None


class AIOrchestrator:
    def __init__(self):
        self.providers: List[Any] = []
        self.provider_health: Dict[Any, bool] = {}
        self.provider_success_rates: Dict[Any, float] = {}
        self.provider_latencies: Dict[Any, List[float]] = {}

        self._init_providers()

    def _init_providers(self):
        try:
            from src.core.deepseek_client import DeepSeekClient
            deepseek = DeepSeekClient()
            deepseek.name = AIProvider.DEEPSEEK.value
            self._register_internal(deepseek)
        except Exception as e:
            logger.debug(f"DeepSeek unavailable: {e}")

        try:
            from .openai_client import OpenAIClient
            if os.getenv("OPENAI_API_KEY"):
                openai_client = OpenAIClient()
                openai_client.name = AIProvider.OPENAI.value
                self._register_internal(openai_client)
        except Exception as e:
            logger.debug(f"OpenAI unavailable: {e}")

        try:
            from .anthropic_client import AnthropicClient
            if os.getenv("ANTHROPIC_API_KEY"):
                anth_client = AnthropicClient()
                anth_client.name = AIProvider.ANTHROPIC.value
                self._register_internal(anth_client)
        except Exception as e:
            logger.debug(f"Anthropic unavailable: {e}")

        rule_based = RuleBasedAnalyzer()
        rule_based.name = AIProvider.RULE_BASED.value
        self._register_internal(rule_based)

    def _register_internal(self, provider: Any):
        self.providers.append(provider)
        self.provider_health[provider] = True
        self.provider_success_rates[provider] = 0.5

    def register_provider(self, provider):
        self.providers.append(provider)
        self.provider_health[provider] = True
        self.provider_success_rates[provider] = 0.5

    def _record_provider_success(self, provider: Any):
        self.provider_success_rates[provider] = self.provider_success_rates.get(provider, 0.5) + 0.1

    def _record_provider_failure(self, provider: Any):
        self.provider_success_rates[provider] = self.provider_success_rates.get(provider, 0.5) - 0.1

    def get_provider_health(self, provider_name: str) -> Dict[str, Any]:
        for provider in self.providers:
            if getattr(provider, "name", "").lower() == provider_name.lower():
                return {
                    "healthy": self.provider_health.get(provider, False),
                    "success_rate": self.provider_success_rates.get(provider, 0.5),
                    "total_calls": 0,
                    "last_success": None,
                    "last_failure": None,
                }
        return {"healthy": False, "success_rate": 0.0, "total_calls": 0, "last_success": None, "last_failure": None}

    async def analyze_with_fallback(self, symbol: str, market_data: Dict, indicators: Dict, strategy_signals: List[Dict]) -> Dict:
        for provider in self.providers:
            if not self.provider_health.get(provider, False):
                continue
            try:
                start = datetime.utcnow()
                result = await self._call_provider(provider, symbol, market_data, indicators, strategy_signals)
                latency = (datetime.utcnow() - start).total_seconds() * 1000
                if result and self._validate_response(result):
                    result["latency_ms"] = latency
                    self._record_provider_success(provider)
                    return result
            except Exception as e:
                logger.warning(f"Provider {getattr(provider, 'name', provider)} failed: {e}")
                self._record_provider_failure(provider)
                self.provider_health[provider] = False

        return {
            "provider": AIProvider.RULE_BASED.value,
            "action": "HOLD",
            "confidence": 0.0,
            "entry_price": None,
            "stop_loss": None,
            "take_profit": None,
            "reasoning": "All AI providers failed",
            "sentiment": "NEUTRAL",
            "success": False,
            "latency_ms": 0.0,
            "error": "All providers failed",
        }

    async def analyze_with_ensemble(self, symbol: str, market_data: Dict, indicators: Dict, strategy_signals: List[Dict]) -> Dict:
        tasks = [self._call_provider(p, symbol, market_data, indicators, strategy_signals) for p in self.providers if self.provider_health.get(p, False)]
        if not tasks:
            return await self.analyze_with_fallback(symbol, market_data, indicators, strategy_signals)

        responses = await asyncio.gather(*tasks, return_exceptions=True)
        valid = []
        for resp in responses:
            if isinstance(resp, Exception):
                continue
            if resp and self._validate_response(resp):
                valid.append(resp)

        if not valid:
            return await self.analyze_with_fallback(symbol, market_data, indicators, strategy_signals)

        return self._aggregate_responses(valid)

    async def _call_provider(self, provider: Any, symbol: str, market_data: Dict, indicators: Dict, strategy_signals: List[Dict]) -> Optional[Dict]:
        if hasattr(provider, "analyze"):
            result = await provider.analyze(symbol, market_data, indicators, strategy_signals)
        else:
            result = await provider.generate_trading_signals(symbol=symbol, market_data=market_data, indicators=indicators, strategy_signals=strategy_signals, sentiment_data={})

        if not result:
            return None

        if isinstance(result, AIResponse):
            return {
                "provider": getattr(result.provider, "value", getattr(provider, "name", "unknown")),
                "action": result.action,
                "confidence": result.confidence,
                "entry_price": result.entry_price,
                "stop_loss": result.stop_loss,
                "take_profit": result.take_profit,
                "reasoning": result.reasoning,
                "sentiment": result.sentiment,
                "success": result.success,
                "latency_ms": result.latency_ms,
                "error": result.error,
            }

        if isinstance(result, dict):
            result.setdefault("provider", getattr(provider, "name", "unknown"))
            return result

        return None

    def _validate_response(self, response: Dict) -> bool:
        action = response.get("action")
        confidence = response.get("confidence", 0)
        entry_price = response.get("entry_price")
        stop_loss = response.get("stop_loss")

        if action not in ["BUY", "SELL", "HOLD"]:
            return False
        if not (0 <= confidence <= 1):
            return False
        if entry_price is not None and entry_price <= 0:
            return False
        if action == "BUY" and stop_loss and entry_price and stop_loss > entry_price:
            return False
        if action == "SELL" and stop_loss and entry_price and stop_loss < entry_price:
            return False
        return True

    def _aggregate_responses(self, responses: List[Dict]) -> Dict:
        if len(responses) == 1:
            return responses[0]

        votes = {"BUY": 0.0, "SELL": 0.0, "HOLD": 0.0}
        for r in responses:
            votes[r.get("action", "HOLD")] += r.get("confidence", 0.0)

        action = max(votes, key=votes.get)
        confidence = votes[action] / max(sum(votes.values()), 1e-6)

        def avg(field: str):
            vals = [r.get(field) for r in responses if r.get(field)]
            return sum(vals) / len(vals) if vals else None

        return {
            "provider": "ensemble",
            "action": action,
            "confidence": confidence,
            "entry_price": avg("entry_price"),
            "stop_loss": avg("stop_loss"),
            "take_profit": avg("take_profit"),
            "reasoning": "Ensemble decision",
            "sentiment": responses[0].get("sentiment", "NEUTRAL"),
            "success": True,
            "latency_ms": max(r.get("latency_ms", 0.0) for r in responses),
            "error": None,
        }

    def get_provider_stats(self) -> Dict:
        stats = {}
        for provider in self.providers:
            stats[getattr(provider, "name", "unknown")] = {
                "healthy": self.provider_health.get(provider, False),
                "success_rate": self.provider_success_rates.get(provider, 0.5),
                "avg_latency_ms": sum(self.provider_latencies.get(provider, [])) / max(len(self.provider_latencies.get(provider, [])), 1) if self.provider_latencies.get(provider) else 0.0,
            }
        return stats


class RuleBasedAnalyzer:
    async def analyze(self, symbol: str, market_data: Dict, indicators: Dict, strategy_signals: List[Dict]) -> Dict:
        buy_signals = sum(1 for s in strategy_signals if s.get("action") == "BUY")
        sell_signals = sum(1 for s in strategy_signals if s.get("action") == "SELL")
        rsi = indicators.get("RSI_14", 50)

        if buy_signals > sell_signals and rsi < 70:
            action = "BUY"
            confidence = 0.7
        elif sell_signals > buy_signals and rsi > 30:
            action = "SELL"
            confidence = 0.7
        else:
            action = "HOLD"
            confidence = 0.3

        current_price = market_data.get("current_price", 0.0)

        return {
            "provider": AIProvider.RULE_BASED.value,
            "action": action,
            "confidence": confidence,
            "entry_price": current_price if current_price else None,
            "stop_loss": current_price * 0.97 if action == "BUY" and current_price else None,
            "take_profit": current_price * 1.03 if action == "BUY" and current_price else None,
            "reasoning": "Rule-based analysis",
            "sentiment": "NEUTRAL",
            "success": True,
            "latency_ms": 0.0,
            "error": None,
        }
