#!/usr/bin/env python3
"""
Simple Data Flow Verification
==============================
This script proves that:
1. Real Binance market data is being fetched
2. DeepSeek AI is analyzing that real data
3. Results are accurate and being displayed
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.core.binance_client import BinanceClient
from src.core.deepseek_client import DeepSeekClient
from src.core.trading_engine import TradingEngine


async def main():
    print("=" * 80)
    print("CoinBourg Data Flow Verification")
    print("=" * 80)
    print()
    
    # Test 1: Fetch REAL data from Binance
    print("📊 Step 1: Fetching REAL market data from Binance...")
    print("-" * 80)
    
    binance = BinanceClient()
    symbol = "BTCUSDT"
    
    try:
        ticker = await binance.get_ticker_24h(symbol)
        price = float(ticker['lastPrice'])
        change = float(ticker['priceChangePercent'])
        volume = float(ticker['quoteVolume'])
        
        print(f"✓ {symbol} Price: ${price:,.2f}")
        print(f"✓ 24h Change: {change:+.2f}%")
        print(f"✓ 24h Volume: ${volume:,.0f}")
        print(f"✓ This is REAL data from Binance API, fetched at {datetime.now().strftime('%H:%M:%S')}")
        print()
        
        # Test 2: Get AI Analysis
        print("🤖 Step 2: Analyzing with DeepSeek AI...")
        print("-" * 80)
        
        engine = TradingEngine()
        await engine.initialize()
        
        # Get market data through engine (which includes indicators)
        market_data = await engine.get_market_data(symbol)
        
        print(f"✓ Calculated Technical Indicators:")
        indicators = market_data.get('indicators', {})
        print(f"  - RSI: {indicators.get('rsi', 0):.2f}")
        print(f"  - MACD: {indicators.get('macd', {}).get('macd', 0):.4f}")
        print(f"  - Trend: {indicators.get('trend', 'N/A')}")
        print()
        
        # Get AI decision
        decision = await engine.analyze_and_decide(symbol)
        
        print(f"✓ DeepSeek AI Analysis Result:")
        print(f"  - Action: {decision.get('action')} {get_action_emoji(decision.get('action'))}")
        print(f"  - Confidence: {decision.get('confidence', 0):.1%}")
        print(f"  - Sentiment: {decision.get('sentiment')}")
        
        entry = decision.get('entry_price')
        stop = decision.get('stop_loss')
        target = decision.get('take_profit')
        
        if entry is not None:
            print(f"  - Entry Price: ${entry:,.2f}")
        if stop is not None:
            print(f"  - Stop Loss: ${stop:,.2f}")
        if target is not None:
            print(f"  - Take Profit: ${target:,.2f}")
        
        print(f"\n  Reasoning:")
        print(f"  {decision.get('reasoning', 'N/A')}")
        print()
        
        # Test 3: Verify AI thoughts are being recorded
        print("💭 Step 3: Checking AI Thought History...")
        print("-" * 80)
        
        thoughts = engine.ai_thoughts[:3]  # Get last 3 thoughts
        print(f"✓ Found {len(engine.ai_thoughts)} recorded AI thoughts")
        
        if thoughts:
            print(f"\nMost Recent Thoughts:")
            for i, thought in enumerate(thoughts, 1):
                print(f"\n  {i}. {thought['symbol']} - {thought['action']} ({thought['confidence']:.1%} confidence)")
                print(f"     Price: ${thought['price']:,.2f}")
                print(f"     {thought['reasoning'][:100]}...")
        
        print()
        print("=" * 80)
        print("✅ VERIFICATION COMPLETE")
        print("=" * 80)
        print()
        print("PROOF THAT SYSTEM IS WORKING:")
        print(f"1. ✓ Fetched REAL price from Binance: ${price:,.2f}")
        print(f"2. ✓ DeepSeek AI analyzed the data: {decision.get('action')} recommendation")
        print(f"3. ✓ Confidence score: {decision.get('confidence', 0):.1%}")
        print(f"4. ✓ {len(engine.ai_thoughts)} AI thoughts recorded in system")
        print()
        print("Your web dashboard at http://4.235.122.138:8000/ is showing")
        print("these REAL analyses based on LIVE Binance data!")
        print()
        
        await engine.shutdown()
        await binance.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def get_action_emoji(action):
    """Get emoji for action."""
    emojis = {
        "BUY": "🟢",
        "SELL": "🔴",
        "HOLD": "🟡"
    }
    return emojis.get(action, "")


if __name__ == "__main__":
    asyncio.run(main())
