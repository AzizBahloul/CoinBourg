#!/bin/bash
# CoinBourg Test Runner
# ====================
# Comprehensive test execution script with coverage reporting.

set -e

echo "========================================="
echo " CoinBourg Test Suite Runner"
echo "========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Activate virtual environment if exists
if [ -d "venv" ]; then
    source venv/bin/activate
elif [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Install test dependencies
echo -e "${YELLOW}Installing test dependencies...${NC}"
pip install -q pytest pytest-asyncio pytest-cov pytest-mock pytest-timeout coverage

# Create test report directory
mkdir -p test_reports

# Function to run specific test suite
run_tests() {
    local test_type=$1
    local test_path=$2
    local marker=$3
    
    echo ""
    echo -e "${YELLOW}Running ${test_type} tests...${NC}"
    echo "--------------------------------------"
    
    if [ -n "$marker" ]; then
        pytest "$test_path" -v -m "$marker" --cov=src --cov-report=term-missing --cov-report=html:test_reports/coverage_${test_type} || true
    else
        pytest "$test_path" -v --cov=src --cov-report=term-missing --cov-report=html:test_reports/coverage_${test_type} || true
    fi
}

# Parse command line arguments
TEST_TYPE=${1:-all}

case $TEST_TYPE in
    unit)
        echo "Running UNIT tests only"
        run_tests "unit" "tests/test_*.py" "unit"
        ;;
    integration)
        echo "Running INTEGRATION tests only"
        run_tests "integration" "tests/test_integration.py" "integration"
        ;;
    core)
        echo "Running CORE module tests"
        run_tests "core" "tests/test_core_comprehensive.py"
        ;;
    binance)
        echo "Running BINANCE CLIENT tests"
        run_tests "binance" "tests/test_binance_client.py"
        ;;
    ai)
        echo "Running AI ORCHESTRATOR tests"
        run_tests "ai" "tests/test_ai_orchestrator.py"
        ;;
    sentiment)
        echo "Running SENTIMENT ANALYZER tests"
        run_tests "sentiment" "tests/test_sentiment_analyzer.py"
        ;;
    coverage)
        echo "Running ALL tests with DETAILED coverage"
        pytest tests/ -v --cov=src --cov-report=term-missing --cov-report=html:test_reports/coverage_full --cov-report=xml:test_reports/coverage.xml
        echo ""
        echo -e "${GREEN}Coverage report generated in test_reports/coverage_full/index.html${NC}"
        ;;
    fast)
        echo "Running FAST tests (no network/database)"
        pytest tests/ -v -m "not network and not database and not slow" --cov=src --cov-report=term-missing
        ;;
    all)
        echo "Running ALL tests"
        echo ""
        
        # Run unit tests
        run_tests "unit" "tests/test_core_comprehensive.py"
        run_tests "binance" "tests/test_binance_client.py"
        run_tests "ai" "tests/test_ai_orchestrator.py"
        run_tests "sentiment" "tests/test_sentiment_analyzer.py"
        
        # Run integration tests
        run_tests "integration" "tests/test_integration.py" "integration"
        
        # Generate combined coverage report
        echo ""
        echo -e "${YELLOW}Generating combined coverage report...${NC}"
        pytest tests/ --cov=src --cov-report=term-missing --cov-report=html:test_reports/coverage_combined
        
        echo ""
        echo -e "${GREEN}✅ All tests completed!${NC}"
        echo -e "${GREEN}Coverage report: test_reports/coverage_combined/index.html${NC}"
        ;;
    *)
        echo "Usage: $0 [unit|integration|core|binance|ai|sentiment|coverage|fast|all]"
        echo ""
        echo "Options:"
        echo "  unit        - Run unit tests only"
        echo "  integration - Run integration tests only"
        echo "  core        - Run core module tests"
        echo "  binance     - Run Binance client tests"
        echo "  ai          - Run AI orchestrator tests"
        echo "  sentiment   - Run sentiment analyzer tests"
        echo "  coverage    - Run all tests with detailed coverage"
        echo "  fast        - Run only fast tests (no network/database)"
        echo "  all         - Run complete test suite (default)"
        exit 1
        ;;
esac

# Display summary
echo ""
echo "========================================="
echo -e "${GREEN} Test Execution Complete ${NC}"
echo "========================================="
echo ""
echo "Test reports available in: test_reports/"
echo ""
echo "To view coverage report:"
echo "  firefox test_reports/coverage_*/index.html"
echo ""
