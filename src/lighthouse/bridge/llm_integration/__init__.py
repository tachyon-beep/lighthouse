"""
LLM Integration Package

Provides integration with external LLM services for expert analysis and validation.
"""

from .expert_llm_client import (
    ExpertType,
    QueryPriority,
    QueryStatus,
    ExpertQuery,
    ExpertResponse,
    ExpertConfig,
    ExpertLLMClient,
    get_expert_llm_client,
    query_security_expert,
    query_code_expert,
    query_architecture_expert
)

__all__ = [
    'ExpertType',
    'QueryPriority', 
    'QueryStatus',
    'ExpertQuery',
    'ExpertResponse',
    'ExpertConfig',
    'ExpertLLMClient',
    'get_expert_llm_client',
    'query_security_expert',
    'query_code_expert',
    'query_architecture_expert'
]