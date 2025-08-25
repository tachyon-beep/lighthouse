"""
Policy Engine Package

Provides OPA-based policy management and evaluation for the Lighthouse system.
"""

from .opa_integration import (
    PolicyDecision,
    PolicyType,
    PolicyScope,
    PolicyQuery,
    PolicyResult,
    PolicyDefinition,
    OPAClient,
    PolicyEngine,
    get_policy_engine,
    evaluate_command_policy,
    evaluate_file_access_policy
)

__all__ = [
    'PolicyDecision',
    'PolicyType',
    'PolicyScope',
    'PolicyQuery',
    'PolicyResult',
    'PolicyDefinition',
    'OPAClient',
    'PolicyEngine',
    'get_policy_engine',
    'evaluate_command_policy',
    'evaluate_file_access_policy'
]