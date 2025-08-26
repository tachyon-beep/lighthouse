#!/bin/bash
# Load Test Scenario Runner
# Usage: ./run_scenario.sh [scenario_name]

set -e

SCENARIO=${1:-"all"}

case $SCENARIO in
    "small")
        echo "🔹 Running small-scale load test (10 agents)..."
        pytest -n 2 -v tests/load/test_multi_agent_load.py::TestMultiAgentLoadScenarios::test_10_agent_coordination
        ;;
    "medium") 
        echo "🔸 Running medium-scale load test (100 agents)..."
        pytest -n 4 -v tests/load/test_multi_agent_load.py::TestMultiAgentLoadScenarios::test_100_agent_coordination
        ;;
    "large")
        echo "🔶 Running large-scale load test (1000+ agents)..."
        pytest -n 8 -v tests/load/test_multi_agent_load.py::TestMultiAgentLoadScenarios::test_1000_agent_coordination
        ;;
    "integrity")
        echo "🔐 Running integrity monitoring tests..."
        pytest -n 4 -v -m integrity tests/load/test_integrated_load_integrity.py
        ;;
    "chaos")
        echo "🌪️ Running chaos engineering tests..."
        pytest -n 2 -v -m chaos tests/load/test_integrated_load_integrity.py
        ;;
    "all"|*)
        echo "🎯 Running all load test scenarios..."
        pytest -n auto -v -m "load or integrity or chaos" tests/load/
        ;;
esac

echo "✅ Load test scenario '$SCENARIO' complete!"
