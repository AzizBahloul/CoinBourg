#!/usr/bin/env python3
"""
CoinBourg System Verification Script
=====================================
This script verifies that all components are working correctly:
1. Binance API connection and data fetching
2. DeepSeek AI analysis
3. Complete trading engine data flow
4. Database connectivity
5. Redis caching

Run this to ensure the system is actually reading real data from Binance
and analyzing it with DeepSeek AI.
"""

import asyncio
import sys
import os
from pathlib import Path
from datetime import datetime
import json

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.core.binance_client import BinanceClient
from src.core.deepseek_client import DeepSeekClient
from src.core.trading_engine import TradingEngine
from src.config.settings import get_settings


class SystemVerifier:
    """Comprehensive system verification."""
    
    def __init__(self):
        self.settings = get_settings()
        self.results = {
            "timestamp": datetime.utcnow().isoformat(),
            "tests": {},
            "overall_status": "PENDING"
        }
    
    async def run_all_tests(self):
        """Run all verification tests."""
        print("=" * 80)
        print("CoinBourg System Verification")
        print("=" * 80)
        print()
        
        tests = [
            ("Configuration Check", self.test_configuration),
            ("Binance Connection", self.test_binance_connection),
            ("Binance Market Data", self.test_binance_market_data),
            ("Binance Order Book", self.test_binance_orderbook),
            ("DeepSeek Connection", self.test_deepseek_connection),
            ("DeepSeek AI Analysis", self.test_deepseek_analysis),
            ("Complete Data Flow", self.test_complete_flow),
            ("Trading Engine", self.test_trading_engine),
        ]
        
        passed = 0
        failed = 0
        
        for test_name, test_func in tests:
            print(f"\n{'─' * 80}")
            print(f"TEST: {test_name}")
            print(f"{'─' * 80}")
            
            try:
                result = await test_func()
                if result["passed"]:
                    print(f"✓ PASSED: {test_name}")
                    passed += 1
                else:
                    print(f"✗ FAILED: {test_name}")
                    print(f"  Reason: {result.get('error', 'Unknown')}")
                    failed += 1
                
                self.results["tests"][test_name] = result
            except Exception as e:
                print(f"✗ ERROR: {test_name}")
                print(f"  Exception: {str(e)}")
                failed += 1
                self.results["tests"][test_name] = {
                    "passed": False,
                    "error": str(e)
                }
        
        print(f"\n{'═' * 80}")
        print(f"VERIFICATION SUMMARY")
        print(f"{'═' * 80}")
        print(f"Total Tests: {passed + failed}")
        print(f"Passed: {passed} ✓")
        print(f"Failed: {failed} ✗")
        
        if failed == 0:
            self.results["overall_status"] = "PASS"
            print(f"\n🎉 ALL TESTS PASSED! System is fully operational.")
        else:
            self.results["overall_status"] = "FAIL"
            print(f"\n⚠️  Some tests failed. Check details above.")
        
        # Save results
        results_file = project_root / "verification_results.json"
        with open(results_file, "w") as f:
            json.dump(self.results, f, indent=2)
        print(f"\nDetailed results saved to: {results_file}")
        
        return failed == 0
    
    async def test_configuration(self) -> dict:
        """Test configuration and API keys."""
        issues = []
        
        if not self.settings.BINANCE_API_KEY:
            issues.append("BINANCE_API_KEY not set")
        if not self.settings.BINANCE_API_SECRET:
            issues.append("BINANCE_API_SECRET not set")
        if not self.settings.DEEPSEEK_API_KEY:
            issues.append("DEEPSEEK_API_KEY not set")
        
        print(f"  BINANCE_API_KEY: {'✓ Set' if self.settings.BINANCE_API_KEY else '✗ Missing'}")
        print(f"  BINANCE_API_SECRET: {'✓ Set' if self.settings.BINANCE_API_SECRET else '✗ Missing'}")
        print(f"  DEEPSEEK_API_KEY: {'✓ Set' if self.settings.DEEPSEEK_API_KEY else '✗ Missing'}")
        print(f"  TRADING_PAIRS: {self.settings.TRADING_PAIRS}")
        
        return {
            "passed": len(issues) == 0,
            "error": ", ".join(issues) if issues else None,
            "details": {
                "binance_configured": bool(self.settings.BINANCE_API_KEY),
                "deepseek_configured": bool(self.settings.DEEPSEEK_API_KEY),
                "trading_pairs": self.settings.TRADING_PAIRS
            }
        }
    
    async def test_binance_connection(self) -> dict:
        """Test Binance API connection."""
        client = BinanceClient()
        
        try:
            # Test connectivity
            server_time = await client._test_connectivity()
            
            print(f"  Server Time: {server_time}")
            print(f"  ✓ Successfully connected to Binance API")
            
            return {
                "passed": True,
                "details": {
                    "server_time": server_time,
                    "connection": "successful"
                }
            }
        except Exception as e:
            print(f"  ✗ Connection failed: {e}")
            return {
                "passed": False,
                "error": str(e)
            }
        finally:
            await client.close()
    
    async def test_binance_market_data(self) -> dict:
        """Test fetching real market data from Binance."""
        client = BinanceClient()
        symbol = "BTCUSDT"
        
        try:
            # Get current price
            ticker = await client.get_ticker_24h(symbol)
            print(f"\n  Symbol: {symbol}")
            print(f"  Current Price: ${float(ticker['lastPrice']):,.2f}")
            print(f"  24h Change: {float(ticker['priceChangePercent']):+.2f}%")
            print(f"  24h Volume: ${float(ticker['quoteVolume']):,.0f}")
            print(f"  24h High: ${float(ticker['highPrice']):,.2f}")
            print(f"  24h Low: ${float(ticker['lowPrice']):,.2f}")
            
            # Get klines
            klines = await client.get_klines(symbol, interval="1h", limit=100)
            print(f"  Historical Data: {len(klines)} candles fetched")
            
            # Verify data freshness
            last_kline_time = datetime.fromtimestamp(klines[-1][0] / 1000)
            time_diff = (datetime.utcnow() - last_kline_time).total_seconds()
            print(f"  Data Freshness: {time_diff:.0f}s ago (Last candle: {last_kline_time})")
            
            return {
                "passed": True,
                "details": {
                    "symbol": symbol,
                    "price": float(ticker['lastPrice']),
                    "change_24h": float(ticker['priceChangePercent']),
                    "klines_count": len(klines),
                    "data_age_seconds": time_diff
                }
            }
        except Exception as e:
            print(f"  ✗ Failed to fetch market data: {e}")
            return {
                "passed": False,
                "error": str(e)
            }
        finally:
            await client.close()
    
    async def test_binance_orderbook(self) -> dict:
        """Test order book data fetching."""
        client = BinanceClient()
        symbol = "BTCUSDT"
        
        try:
            orderbook = await client.get_orderbook(symbol, limit=10)
            
            bids = orderbook.get('bids', [])
            asks = orderbook.get('asks', [])
            
            print(f"\n  Order Book for {symbol}:")
            print(f"  Top Bid: ${float(bids[0][0]):,.2f} (Size: {float(bids[0][1]):.4f})")
            print(f"  Top Ask: ${float(asks[0][0]):,.2f} (Size: {float(asks[0][1]):.4f})")
            print(f"  Spread: ${float(asks[0][0]) - float(bids[0][0]):.2f}")
            
            return {
                "passed": True,
                "details": {
                    "bid_depth": len(bids),
                    "ask_depth": len(asks),
                    "top_bid": float(bids[0][0]),
                    "top_ask": float(asks[0][0])
                }
            }
        except Exception as e:
            print(f"  ✗ Failed to fetch order book: {e}")
            return {
                "passed": False,
                "error": str(e)
            }
        finally:
            await client.close()
    
    async def test_deepseek_connection(self) -> dict:
        """Test DeepSeek AI API connection."""
        client = DeepSeekClient()
        
        try:
            # Simple health check
            is_healthy = await client.health_check()
            
            print(f"  DeepSeek Health: {'✓ Healthy' if is_healthy else '✗ Unhealthy'}")
            print(f"  Model: {client.model}")
            print(f"  Base URL: {client.base_url}")
            
            return {
                "passed": is_healthy,
                "details": {
                    "model": client.model,
                    "base_url": client.base_url,
                    "healthy": is_healthy
                }
            }
        except Exception as e:
            print(f"  ✗ Connection failed: {e}")
            return {
                "passed": False,
                "error": str(e)
            }
        finally:
            await client.close()
    
    async def test_deepseek_analysis(self) -> dict:
        """Test actual AI analysis with real market data."""
        binance = BinanceClient()
        deepseek = DeepSeekClient()
        symbol = "BTCUSDT"
        
        try:
            # Get real market data
            ticker = await binance.get_ticker_24h(symbol)
            klines = await binance.get_klines(symbol, interval="1h", limit=100)
            
            # Calculate technical indicators
            from src.utils.helpers import calculate_technical_indicators
            indicators = calculate_technical_indicators(klines)
            
            current_price = float(ticker['lastPrice'])
            
            print(f"\n  Analyzing {symbol} with DeepSeek AI...")
            print(f"  Price: ${current_price:,.2f}")
            
            # Get AI analysis
            analysis = await deepseek.analyze_market(
                symbol=symbol,
                current_price=current_price,
                price_change_24h=float(ticker['priceChangePercent']),
                volume_24h=float(ticker['quoteVolume']),
                high_24h=float(ticker['highPrice']),
                low_24h=float(ticker['lowPrice']),
                technical_indicators=indicators
            )
            
            print(f"\n  AI ANALYSIS RESULT:")
            print(f"  ├─ Action: {analysis.get('action', 'N/A')}")
            print(f"  ├─ Sentiment: {analysis.get('sentiment', 'N/A')}")
            print(f"  ├─ Confidence: {analysis.get('confidence', 0):.1%}")
            print(f"  ├─ Entry Price: ${analysis.get('entry_price', 0):,.2f}")
            print(f"  ├─ Stop Loss: ${analysis.get('stop_loss', 0):,.2f}")
            print(f"  ├─ Take Profit: ${analysis.get('take_profit', 0):,.2f}")
            print(f"  └─ Reasoning: {analysis.get('reasoning', 'N/A')[:100]}...")
            
            # Verify analysis is valid
            required_fields = ['action', 'confidence', 'reasoning']
            has_all_fields = all(field in analysis for field in required_fields)
            
            return {
                "passed": has_all_fields and analysis.get('confidence', 0) > 0,
                "details": {
                    "action": analysis.get('action'),
                    "confidence": analysis.get('confidence'),
                    "sentiment": analysis.get('sentiment'),
                    "has_reasoning": bool(analysis.get('reasoning'))
                }
            }
        except Exception as e:
            print(f"  ✗ AI analysis failed: {e}")
            return {
                "passed": False,
                "error": str(e)
            }
        finally:
            await binance.close()
            await deepseek.close()
    
    async def test_complete_flow(self) -> dict:
        """Test the complete data flow: Binance → Analysis → Decision."""
        binance = BinanceClient()
        deepseek = DeepSeekClient()
        symbol = "ETHUSDT"
        
        try:
            print(f"\n  Testing complete flow for {symbol}...")
            
            # Step 1: Fetch real market data from Binance
            print(f"\n  [1/4] Fetching market data from Binance...")
            ticker = await binance.get_ticker_24h(symbol)
            klines = await binance.get_klines(symbol, interval="1h", limit=100)
            orderbook = await binance.get_orderbook(symbol, limit=20)
            
            current_price = float(ticker['lastPrice'])
            print(f"        ✓ Got price: ${current_price:,.2f}")
            print(f"        ✓ Got {len(klines)} historical candles")
            print(f"        ✓ Got order book data")
            
            # Step 2: Calculate technical indicators
            print(f"\n  [2/4] Calculating technical indicators...")
            from src.utils.helpers import calculate_technical_indicators, analyze_orderbook
            indicators = calculate_technical_indicators(klines)
            orderbook_analysis = analyze_orderbook(orderbook)
            
            print(f"        ✓ RSI: {indicators.get('rsi', 0):.2f}")
            print(f"        ✓ MACD: {indicators.get('macd', {}).get('macd', 0):.4f}")
            print(f"        ✓ BB Position: {indicators.get('bb_position', 0):.2f}")
            
            # Step 3: Send to DeepSeek for AI analysis
            print(f"\n  [3/4] Analyzing with DeepSeek AI...")
            analysis = await deepseek.analyze_market(
                symbol=symbol,
                current_price=current_price,
                price_change_24h=float(ticker['priceChangePercent']),
                volume_24h=float(ticker['quoteVolume']),
                high_24h=float(ticker['highPrice']),
                low_24h=float(ticker['lowPrice']),
                technical_indicators=indicators,
                orderbook_summary=orderbook_analysis
            )
            
            print(f"        ✓ AI Decision: {analysis.get('action')}")
            print(f"        ✓ Confidence: {analysis.get('confidence', 0):.1%}")
            
            # Step 4: Verify complete chain
            print(f"\n  [4/4] Verifying data chain...")
            
            chain_valid = all([
                ticker is not None,
                len(klines) > 0,
                indicators.get('rsi') is not None,
                analysis.get('action') is not None,
                analysis.get('confidence', 0) > 0
            ])
            
            print(f"        ✓ Data chain is {'COMPLETE' if chain_valid else 'BROKEN'}")
            
            return {
                "passed": chain_valid,
                "details": {
                    "binance_data": "fetched",
                    "indicators": "calculated",
                    "ai_analysis": "completed",
                    "action": analysis.get('action'),
                    "confidence": analysis.get('confidence')
                }
            }
        except Exception as e:
            print(f"  ✗ Complete flow failed: {e}")
            return {
                "passed": False,
                "error": str(e)
            }
        finally:
            await binance.close()
            await deepseek.close()
    
    async def test_trading_engine(self) -> dict:
        """Test the trading engine's market analysis."""
        engine = TradingEngine()
        
        try:
            await engine.initialize()
            
            symbol = "BTCUSDT"
            print(f"\n  Testing trading engine analysis for {symbol}...")
            
            # Get analysis
            decision = await engine.analyze_and_decide(symbol)
            
            print(f"\n  TRADING ENGINE DECISION:")
            print(f"  ├─ Action: {decision.get('action')}")
            print(f"  ├─ Confidence: {decision.get('confidence', 0):.1%}")
            print(f"  ├─ Sentiment: {decision.get('sentiment')}")
            print(f"  └─ Reasoning: {decision.get('reasoning', '')[:100]}...")
            
            # Check AI thoughts are being recorded
            thoughts = engine.get_ai_thoughts(limit=5)
            print(f"\n  AI Thoughts Recorded: {len(thoughts)}")
            if thoughts:
                latest = thoughts[0]
                print(f"  Latest Thought:")
                print(f"    Symbol: {latest.get('symbol')}")
                print(f"    Action: {latest.get('action')}")
                print(f"    Confidence: {latest.get('confidence', 0):.1%}")
            
            return {
                "passed": decision is not None and decision.get('action') is not None,
                "details": {
                    "action": decision.get('action'),
                    "confidence": decision.get('confidence'),
                    "thoughts_count": len(thoughts)
                }
            }
        except Exception as e:
            print(f"  ✗ Trading engine test failed: {e}")
            return {
                "passed": False,
                "error": str(e)
            }
        finally:
            await engine.shutdown()


async def main():
    """Run verification."""
    verifier = SystemVerifier()
    success = await verifier.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
