"""
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
