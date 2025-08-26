#!/usr/bin/env python3
"""
Load Testing Setup Script
Phase 1 Days 8-10: Setup pytest-xdist parallel execution and load testing environment

This script:
- Installs pytest-xdist for parallel test execution
- Configures load testing environment
- Sets up monitoring and metrics collection
- Validates system readiness for load testing
"""

import os
import sys
import subprocess
import asyncio
import tempfile
import shutil
from pathlib import Path

def install_dependencies():
    """Install required dependencies for load testing"""
    print("📦 Installing load testing dependencies...")
    
    dependencies = [
        'pytest-xdist>=3.0.0',        # Parallel test execution
        'pytest-asyncio>=0.21.0',     # Async test support  
        'psutil>=5.8.0',               # System monitoring
        'hypothesis>=6.0.0',           # Property-based testing
        'pytest-benchmark>=4.0.0',    # Performance benchmarking
        'pytest-cov>=4.0.0',          # Coverage reporting
        'pytest-html>=3.0.0',         # HTML test reports
        'pytest-timeout>=2.0.0',      # Test timeout handling
        'pytest-mock>=3.0.0'          # Mocking utilities
    ]
    
    for dep in dependencies:
        try:
            print(f"  Installing {dep}...")
            subprocess.run([sys.executable, '-m', 'pip', 'install', dep], 
                         check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            print(f"  ⚠️  Failed to install {dep}: {e}")
            print(f"     You may need to install manually: pip install {dep}")
    
    print("✅ Dependencies installation complete")


def setup_test_directories():
    """Setup test directory structure for load testing"""
    print("📁 Setting up test directories...")
    
    test_dirs = [
        'tests/load',
        'tests/load/data',
        'tests/load/reports',
        'tests/load/logs',
        'tests/performance',
        'tests/chaos',
        'tests/integrity',
        'src/lighthouse/integrity'
    ]
    
    for test_dir in test_dirs:
        Path(test_dir).mkdir(parents=True, exist_ok=True)
        
        # Create __init__.py files for Python modules
        init_file = Path(test_dir) / '__init__.py'
        if not init_file.exists() and 'src/' not in test_dir:
            init_file.write_text("# Load testing module\n")
    
    print("✅ Test directories created")


def create_xdist_configuration():
    """Create pytest-xdist configuration for parallel execution"""
    print("⚙️ Creating pytest-xdist configuration...")
    
    # Create conftest.py for xdist configuration
    conftest_content = '''"""
Load Testing Configuration for pytest-xdist parallel execution
"""

import pytest
import asyncio
import os
import tempfile
from pathlib import Path

# pytest-xdist parallel execution configuration

def pytest_configure(config):
    """Configure pytest for parallel execution"""
    # Ensure worker-specific temporary directories
    if hasattr(config, 'workerinput'):
        worker_id = config.workerinput.get('workerid', 'master')
        
        # Create worker-specific temp directory
        worker_tmp = Path(tempfile.gettempdir()) / f"lighthouse_load_test_{worker_id}"
        worker_tmp.mkdir(exist_ok=True)
        
        # Set environment variables for worker
        os.environ[f'LIGHTHOUSE_WORKER_ID'] = worker_id
        os.environ[f'LIGHTHOUSE_WORKER_TMP'] = str(worker_tmp)


def pytest_unconfigure(config):
    """Cleanup after pytest execution"""
    if hasattr(config, 'workerinput'):
        worker_id = config.workerinput.get('workerid', 'master')
        
        # Cleanup worker temp directory
        worker_tmp = Path(tempfile.gettempdir()) / f"lighthouse_load_test_{worker_id}"
        if worker_tmp.exists():
            try:
                import shutil
                shutil.rmtree(worker_tmp)
            except:
                pass


@pytest.fixture(scope="session")
def xdist_worker_id():
    """Provide worker ID for parallel test execution"""
    return os.environ.get('LIGHTHOUSE_WORKER_ID', 'master')


@pytest.fixture(scope="session") 
def xdist_worker_tmp():
    """Provide worker-specific temporary directory"""
    return os.environ.get('LIGHTHOUSE_WORKER_TMP', tempfile.gettempdir())


# Load testing fixtures for parallel execution

@pytest.fixture(scope="session")
async def shared_load_test_bridge():
    """Shared bridge instance for load testing across workers"""
    try:
        from lighthouse.bridge.main_bridge import LighthouseBridge
        
        bridge = LighthouseBridge(config={
            'auth_secret': 'load_test_secret',
            'fuse_mount_point': f'/tmp/lighthouse_load_test_{os.getpid()}'
        })
        
        yield bridge
        
        # Cleanup
        if hasattr(bridge, 'close'):
            await bridge.close()
            
    except ImportError:
        # Mock bridge if not available
        from unittest.mock import Mock
        yield Mock()


@pytest.fixture
async def isolated_load_test_environment(xdist_worker_tmp):
    """Isolated test environment for each worker"""
    # Create isolated environment
    test_env = {
        'worker_tmp': xdist_worker_tmp,
        'fuse_mount': f'{xdist_worker_tmp}/fuse_mount',
        'event_store': f'{xdist_worker_tmp}/event_store.db',
        'logs': f'{xdist_worker_tmp}/logs'
    }
    
    # Setup directories
    for path in test_env.values():
        if isinstance(path, str):
            Path(path).parent.mkdir(parents=True, exist_ok=True)
    
    yield test_env
    
    # Cleanup is handled by pytest_unconfigure


# Parallel execution helpers

def get_worker_count():
    """Get optimal worker count for parallel execution"""
    import multiprocessing
    cpu_count = multiprocessing.cpu_count()
    
    # Use 75% of available CPUs for load testing
    return max(1, int(cpu_count * 0.75))


def is_xdist_master():
    """Check if running on xdist master process"""
    return os.environ.get('LIGHTHOUSE_WORKER_ID', 'master') == 'master'


def is_xdist_worker():
    """Check if running on xdist worker process"""
    return os.environ.get('LIGHTHOUSE_WORKER_ID', 'master') != 'master'
'''
    
    with open('tests/conftest.py', 'w') as f:
        f.write(conftest_content)
    
    print("✅ pytest-xdist configuration created")


def create_load_testing_scripts():
    """Create load testing execution scripts"""
    print("📜 Creating load testing scripts...")
    
    # Script for running parallel load tests
    parallel_script = '''#!/bin/bash
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
pytest -n $WORKER_COUNT \\
    --verbose \\
    --tb=short \\
    --durations=10 \\
    --html=tests/load/reports/load_test_report.html \\
    --self-contained-html \\
    --cov=lighthouse \\
    --cov-report=html:tests/load/reports/coverage \\
    --cov-report=term \\
    --timeout=300 \\
    --markers="load or integrity or chaos" \\
    $TEST_PATTERN

echo "✅ Parallel load testing complete!"
echo "📊 Reports available at: tests/load/reports/"
'''
    
    with open('scripts/run_load_tests.sh', 'w') as f:
        f.write(parallel_script)
    
    os.chmod('scripts/run_load_tests.sh', 0o755)
    
    # Script for running specific load test scenarios
    scenario_script = '''#!/bin/bash
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
'''
    
    with open('scripts/run_scenario.sh', 'w') as f:
        f.write(scenario_script)
    
    os.chmod('scripts/run_scenario.sh', 0o755)
    
    print("✅ Load testing scripts created")


def validate_environment():
    """Validate system readiness for load testing"""
    print("🔍 Validating load testing environment...")
    
    validation_results = {
        'python_version': sys.version_info >= (3, 8),
        'pytest_available': False,
        'xdist_available': False,
        'psutil_available': False,
        'asyncio_available': True,
        'temp_dir_writable': False,
        'cpu_cores': 0,
        'memory_gb': 0
    }
    
    # Check pytest availability
    try:
        import pytest
        validation_results['pytest_available'] = True
    except ImportError:
        pass
    
    # Check pytest-xdist
    try:
        import xdist
        validation_results['xdist_available'] = True
    except ImportError:
        pass
    
    # Check psutil
    try:
        import psutil
        validation_results['psutil_available'] = True
        validation_results['cpu_cores'] = psutil.cpu_count()
        validation_results['memory_gb'] = psutil.virtual_memory().total / (1024**3)
    except ImportError:
        pass
    
    # Check temp directory
    try:
        with tempfile.NamedTemporaryFile(delete=True) as tmp:
            validation_results['temp_dir_writable'] = True
    except:
        pass
    
    # Print validation results
    print("  Validation Results:")
    for check, result in validation_results.items():
        status = "✅" if result else "❌"
        if check in ['cpu_cores', 'memory_gb'] and result:
            print(f"    {status} {check}: {result}")
        else:
            print(f"    {status} {check}: {result}")
    
    # Check for critical issues
    critical_issues = []
    if not validation_results['python_version']:
        critical_issues.append("Python 3.8+ required")
    if not validation_results['pytest_available']:
        critical_issues.append("pytest not available")
    if not validation_results['temp_dir_writable']:
        critical_issues.append("Temporary directory not writable")
    
    if critical_issues:
        print("\n❌ Critical Issues Found:")
        for issue in critical_issues:
            print(f"  - {issue}")
        return False
    
    # Warnings for non-critical issues
    warnings = []
    if not validation_results['xdist_available']:
        warnings.append("pytest-xdist not available - parallel execution disabled")
    if not validation_results['psutil_available']:
        warnings.append("psutil not available - system monitoring limited")
    if validation_results['cpu_cores'] < 4:
        warnings.append("Less than 4 CPU cores - parallel execution may be limited")
    if validation_results['memory_gb'] < 4:
        warnings.append("Less than 4GB RAM - large-scale tests may fail")
    
    if warnings:
        print("\n⚠️ Warnings:")
        for warning in warnings:
            print(f"  - {warning}")
    
    print("\n✅ Environment validation complete")
    return True


async def run_smoke_test():
    """Run smoke test to verify load testing framework"""
    print("🧪 Running load testing smoke test...")
    
    try:
        # Import our load testing framework
        sys.path.insert(0, 'tests/load')
        from test_multi_agent_load import MultiAgentLoadTestFramework
        
        # Create simple load test
        framework = MultiAgentLoadTestFramework()
        
        # Small-scale smoke test
        agent_configs = [
            {'type': 'smoke_test', 'command_rate': 1.0, 'complexity': 'low'}
            for _ in range(3)
        ]
        
        framework.create_agent_pool(agent_configs)
        
        print("  Running 3-agent smoke test for 10 seconds...")
        metrics = await framework.run_load_test(duration_seconds=10)
        
        print(f"  Results: {metrics.total_agents} agents, {metrics.avg_response_time:.3f}s avg response")
        print(f"  Errors: {metrics.error_rate:.1%}, Memory: {metrics.memory_peak_mb:.1f}MB")
        
        # Validate smoke test results
        assert metrics.total_agents == 3
        assert metrics.avg_response_time < 1.0  # <1s for smoke test
        assert metrics.error_rate < 0.1  # <10% errors
        
        print("✅ Smoke test passed!")
        return True
        
    except Exception as e:
        print(f"❌ Smoke test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main setup function"""
    print("🚀 Setting up Phase 1 Days 8-10 Load Testing Environment")
    print("=" * 60)
    
    try:
        # Step 1: Install dependencies
        install_dependencies()
        print()
        
        # Step 2: Setup directories
        setup_test_directories() 
        print()
        
        # Step 3: Create xdist configuration
        create_xdist_configuration()
        print()
        
        # Step 4: Create scripts
        create_load_testing_scripts()
        print()
        
        # Step 5: Validate environment
        if not validate_environment():
            print("\n❌ Environment validation failed!")
            sys.exit(1)
        print()
        
        # Step 6: Run smoke test
        loop = asyncio.get_event_loop()
        if not loop.run_until_complete(run_smoke_test()):
            print("\n❌ Smoke test failed!")
            sys.exit(1)
        
        print()
        print("🎉 Load Testing Setup Complete!")
        print("=" * 60)
        print("Next steps:")
        print("  1. Run small-scale test: ./scripts/run_scenario.sh small")
        print("  2. Run full load tests: ./scripts/run_load_tests.sh")
        print("  3. View reports: tests/load/reports/")
        print("\nParallel execution commands:")
        print("  - pytest -n auto tests/load/          # Auto-detect workers")
        print("  - pytest -n 4 tests/load/             # Use 4 workers")
        print("  - pytest -n 2 -m integrity tests/load/ # Integrity tests only")
        
    except Exception as e:
        print(f"\n❌ Setup failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()