#!/bin/bash
# Parallel Load Testing Script
# Usage: ./run_load_tests.sh [test_pattern] [worker_count]

set -e

TEST_PATTERN=${1:-"tests/load/"}
WORKER_COUNT=${2:-"auto"}

echo "🚀 Starting parallel load testing..."
echo "  Pattern: $TEST_PATTERN"
echo "  Workers: $WORKER_COUNT"

# Create reports directory
mkdir -p tests/load/reports

# Run parallel tests with xdist
pytest -n $WORKER_COUNT \
    --verbose \
    --tb=short \
    --durations=10 \
    --html=tests/load/reports/load_test_report.html \
    --self-contained-html \
    --cov=lighthouse \
    --cov-report=html:tests/load/reports/coverage \
    --cov-report=term \
    --timeout=300 \
    --markers="load or integrity or chaos" \
    $TEST_PATTERN

echo "✅ Parallel load testing complete!"
echo "📊 Reports available at: tests/load/reports/"
