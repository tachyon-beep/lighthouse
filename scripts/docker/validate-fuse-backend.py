#!/usr/bin/env python3
"""
FUSE Backend Validation Script
Used by health checks to verify FUSE backend is operational
"""

import os
import sys
import importlib
import json
from datetime import datetime
from pathlib import Path

def check_backend(backend_name: str) -> dict:
    """Check if a specific FUSE backend is available and functional"""
    result = {
        "backend": backend_name,
        "available": False,
        "functional": False,
        "version": None,
        "errors": []
    }
    
    try:
        if backend_name == "fusepy":
            import fuse
            result["available"] = True
            
            # Check if we can import the main classes
            from fuse import FUSE, FuseOSError, Operations
            result["functional"] = True
            
            # Try to get version
            result["version"] = getattr(fuse, '__version__', 'unknown')
            
            # Check for libfuse2
            libfuse2_path = Path("/usr/lib/x86_64-linux-gnu/libfuse.so.2")
            if not libfuse2_path.exists():
                result["errors"].append("libfuse2 library not found")
                result["functional"] = False
                
        elif backend_name == "pyfuse3":
            import pyfuse3
            result["available"] = True
            
            # Check for required async runtime
            import trio
            result["functional"] = True
            
            # Get version
            result["version"] = pyfuse3.__version__
            
            # Check for libfuse3
            libfuse3_path = Path("/usr/lib/x86_64-linux-gnu/libfuse3.so.3")
            if not libfuse3_path.exists():
                result["errors"].append("libfuse3 library not found")
                result["functional"] = False
                
        else:
            result["errors"].append(f"Unknown backend: {backend_name}")
            
    except ImportError as e:
        result["errors"].append(f"Import failed: {str(e)}")
    except Exception as e:
        result["errors"].append(f"Unexpected error: {str(e)}")
    
    return result

def validate_active_backend():
    """Validate the currently active FUSE backend"""
    
    # Get configured backend from environment
    active_backend = os.environ.get("LIGHTHOUSE_ACTIVE_FUSE_BACKEND", "none")
    
    if active_backend == "none":
        print("WARNING: No FUSE backend configured", file=sys.stderr)
        sys.exit(0)  # Not an error - degraded mode is acceptable
    
    # Check the active backend
    result = check_backend(active_backend)
    
    # Output validation results
    validation = {
        "timestamp": datetime.utcnow().isoformat(),
        "configured_backend": active_backend,
        "validation": result
    }
    
    # Also check both backends if in benchmark/test mode
    if os.environ.get("LIGHTHOUSE_FUSE_BENCHMARK") == "true" or \
       os.environ.get("LIGHTHOUSE_FUSE_PARALLEL_TEST") == "true":
        validation["all_backends"] = {
            "fusepy": check_backend("fusepy"),
            "pyfuse3": check_backend("pyfuse3")
        }
    
    # Print JSON result
    print(json.dumps(validation, indent=2))
    
    # Exit with appropriate code
    if result["functional"]:
        print(f"✅ Backend '{active_backend}' is functional", file=sys.stderr)
        sys.exit(0)
    else:
        print(f"❌ Backend '{active_backend}' is not functional: {result['errors']}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    validate_active_backend()