"""
Expert LLM Client Integration

Provides integration with external expert LLM services for specialized
validation, analysis, and decision-making within the Lighthouse system.

Part of Plan Charlie Phase 2 implementation.
"""

import asyncio
import json
import logging
import hashlib
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Union, Callable
import aiohttp
import os

logger = logging.getLogger(__name__)


class ExpertType(Enum):
    """Types of expert LLM services."""
    SECURITY_ANALYST = "security_analyst"
    CODE_REVIEWER = "code_reviewer"
    ARCHITECTURE_VALIDATOR = "architecture_validator"
    PERFORMANCE_ANALYST = "performance_analyst"
    COMPLIANCE_AUDITOR = "compliance_auditor"
    THREAT_MODELER = "threat_modeler"
    GENERAL_ADVISOR = "general_advisor"


class QueryPriority(Enum):
    """Priority levels for expert queries."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class QueryStatus(Enum):
    """Status of expert queries."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class ExpertQuery:
    """Represents a query to an expert LLM service."""
    query_id: str
    expert_type: ExpertType
    query_text: str
    context: Dict[str, Any]
    priority: QueryPriority
    timeout_seconds: int
    created_at: datetime
    status: QueryStatus = QueryStatus.PENDING
    response: Optional[str] = None
    confidence: Optional[float] = None
    processing_time_ms: Optional[float] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = asdict(self)
        data['expert_type'] = self.expert_type.value
        data['priority'] = self.priority.value
        data['status'] = self.status.value
        data['created_at'] = self.created_at.isoformat()
        return data


@dataclass
class ExpertResponse:
    """Response from an expert LLM service."""
    query_id: str
    expert_type: ExpertType
    response_text: str
    confidence: float  # 0.0 to 1.0
    reasoning: Optional[str]
    recommendations: List[str]
    metadata: Dict[str, Any]
    processing_time_ms: float
    timestamp: datetime
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = asdict(self)
        data['expert_type'] = self.expert_type.value
        data['timestamp'] = self.timestamp.isoformat()
        return data


@dataclass
class ExpertConfig:
    """Configuration for an expert LLM service."""
    expert_type: ExpertType
    endpoint_url: str
    api_key: Optional[str]
    model_name: str
    max_tokens: int
    temperature: float
    timeout_seconds: int
    retry_attempts: int
    rate_limit_per_minute: int
    system_prompt: str
    enabled: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = asdict(self)
        data['expert_type'] = self.expert_type.value
        return data


class ExpertLLMProvider(ABC):
    """Abstract base class for expert LLM providers."""
    
    @abstractmethod
    async def query_expert(self, query: ExpertQuery, config: ExpertConfig) -> ExpertResponse:
        """Query the expert LLM service."""
        pass
    
    @abstractmethod
    async def health_check(self, config: ExpertConfig) -> bool:
        """Check if the expert service is healthy."""
        pass


class AnthropicExpertProvider(ExpertLLMProvider):
    """Expert LLM provider for Anthropic Claude services."""
    
    def __init__(self):
        """Initialize Anthropic provider."""
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def query_expert(self, query: ExpertQuery, config: ExpertConfig) -> ExpertResponse:
        """Query Anthropic Claude expert."""
        start_time = time.time()
        
        session = await self._get_session()
        
        headers = {
            "Content-Type": "application/json",
            "x-api-key": config.api_key or "",
            "anthropic-version": "2023-06-01"
        }
        
        payload = {
            "model": config.model_name,
            "max_tokens": config.max_tokens,
            "temperature": config.temperature,
            "system": config.system_prompt,
            "messages": [
                {
                    "role": "user",
                    "content": self._format_query_for_anthropic(query)
                }
            ]
        }
        
        try:
            timeout = aiohttp.ClientTimeout(total=config.timeout_seconds)
            
            async with session.post(
                config.endpoint_url,
                headers=headers,
                json=payload,
                timeout=timeout
            ) as response:
                
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"API error {response.status}: {error_text}")
                
                result = await response.json()
                processing_time = (time.time() - start_time) * 1000
                
                return self._parse_anthropic_response(query, result, processing_time)
                
        except asyncio.TimeoutError:
            raise Exception("Query timeout")
        except Exception as e:
            logger.error(f"Anthropic query failed: {str(e)}")
            raise
    
    def _format_query_for_anthropic(self, query: ExpertQuery) -> str:
        """Format query for Anthropic API."""
        context_str = json.dumps(query.context, indent=2) if query.context else "None"
        
        return f"""
Expert Analysis Request:
Type: {query.expert_type.value}
Priority: {query.priority.value}

Query: {query.query_text}

Context:
{context_str}

Please provide:
1. Your analysis and response
2. Confidence level (0.0-1.0)
3. Reasoning behind your assessment
4. Specific recommendations if applicable

Format your response as JSON with fields:
- analysis: your detailed analysis
- confidence: confidence level as a number
- reasoning: your reasoning process
- recommendations: list of specific recommendations
"""
    
    def _parse_anthropic_response(self, query: ExpertQuery, result: Dict, processing_time: float) -> ExpertResponse:
        """Parse Anthropic API response."""
        content = result.get("content", [])
        if not content:
            raise Exception("Empty response from Anthropic")
        
        response_text = content[0].get("text", "")
        
        # Try to parse as JSON first
        try:
            parsed = json.loads(response_text)
            analysis = parsed.get("analysis", response_text)
            confidence = float(parsed.get("confidence", 0.5))
            reasoning = parsed.get("reasoning", "")
            recommendations = parsed.get("recommendations", [])
        except (json.JSONDecodeError, ValueError):
            # Fallback to text parsing
            analysis = response_text
            confidence = 0.5  # Default confidence
            reasoning = ""
            recommendations = []
        
        return ExpertResponse(
            query_id=query.query_id,
            expert_type=query.expert_type,
            response_text=analysis,
            confidence=confidence,
            reasoning=reasoning,
            recommendations=recommendations if isinstance(recommendations, list) else [],
            metadata={
                "model": result.get("model", "unknown"),
                "usage": result.get("usage", {})
            },
            processing_time_ms=processing_time,
            timestamp=datetime.utcnow()
        )
    
    async def health_check(self, config: ExpertConfig) -> bool:
        """Check Anthropic service health."""
        try:
            # Simple test query
            test_query = ExpertQuery(
                query_id="health_check",
                expert_type=config.expert_type,
                query_text="Health check - please respond with 'OK'",
                context={},
                priority=QueryPriority.LOW,
                timeout_seconds=10,
                created_at=datetime.utcnow()
            )
            
            response = await self.query_expert(test_query, config)
            return "ok" in response.response_text.lower()
            
        except Exception as e:
            logger.warning(f"Health check failed for {config.expert_type.value}: {str(e)}")
            return False
    
    async def close(self):
        """Close the session."""
        if self.session:
            await self.session.close()
            self.session = None


class OpenAIExpertProvider(ExpertLLMProvider):
    """Expert LLM provider for OpenAI services."""
    
    def __init__(self):
        """Initialize OpenAI provider."""
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def query_expert(self, query: ExpertQuery, config: ExpertConfig) -> ExpertResponse:
        """Query OpenAI expert."""
        start_time = time.time()
        
        session = await self._get_session()
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.api_key or ''}"
        }
        
        payload = {
            "model": config.model_name,
            "messages": [
                {"role": "system", "content": config.system_prompt},
                {"role": "user", "content": self._format_query_for_openai(query)}
            ],
            "max_tokens": config.max_tokens,
            "temperature": config.temperature
        }
        
        try:
            timeout = aiohttp.ClientTimeout(total=config.timeout_seconds)
            
            async with session.post(
                config.endpoint_url,
                headers=headers,
                json=payload,
                timeout=timeout
            ) as response:
                
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"API error {response.status}: {error_text}")
                
                result = await response.json()
                processing_time = (time.time() - start_time) * 1000
                
                return self._parse_openai_response(query, result, processing_time)
                
        except asyncio.TimeoutError:
            raise Exception("Query timeout")
        except Exception as e:
            logger.error(f"OpenAI query failed: {str(e)}")
            raise
    
    def _format_query_for_openai(self, query: ExpertQuery) -> str:
        """Format query for OpenAI API."""
        context_str = json.dumps(query.context, indent=2) if query.context else "None"
        
        return f"""
Expert Analysis Request:
Type: {query.expert_type.value}
Priority: {query.priority.value}

Query: {query.query_text}

Context:
{context_str}

Please provide your analysis with confidence level and recommendations.
"""
    
    def _parse_openai_response(self, query: ExpertQuery, result: Dict, processing_time: float) -> ExpertResponse:
        """Parse OpenAI API response."""
        choices = result.get("choices", [])
        if not choices:
            raise Exception("Empty response from OpenAI")
        
        response_text = choices[0].get("message", {}).get("content", "")
        
        return ExpertResponse(
            query_id=query.query_id,
            expert_type=query.expert_type,
            response_text=response_text,
            confidence=0.7,  # Default confidence for OpenAI
            reasoning="OpenAI analysis",
            recommendations=[],
            metadata={
                "model": result.get("model", "unknown"),
                "usage": result.get("usage", {})
            },
            processing_time_ms=processing_time,
            timestamp=datetime.utcnow()
        )
    
    async def health_check(self, config: ExpertConfig) -> bool:
        """Check OpenAI service health."""
        try:
            test_query = ExpertQuery(
                query_id="health_check",
                expert_type=config.expert_type,
                query_text="Health check - please respond with 'OK'",
                context={},
                priority=QueryPriority.LOW,
                timeout_seconds=10,
                created_at=datetime.utcnow()
            )
            
            response = await self.query_expert(test_query, config)
            return len(response.response_text) > 0
            
        except Exception as e:
            logger.warning(f"Health check failed for {config.expert_type.value}: {str(e)}")
            return False
    
    async def close(self):
        """Close the session."""
        if self.session:
            await self.session.close()
            self.session = None


class ExpertLLMClient:
    """Main Expert LLM client for managing expert queries."""
    
    def __init__(self):
        """Initialize expert LLM client."""
        self.providers: Dict[str, ExpertLLMProvider] = {
            "anthropic": AnthropicExpertProvider(),
            "openai": OpenAIExpertProvider()
        }
        
        self.configs: Dict[ExpertType, ExpertConfig] = {}
        self.query_queue: List[ExpertQuery] = []
        self.active_queries: Dict[str, ExpertQuery] = {}
        self.completed_queries: Dict[str, ExpertResponse] = {}
        
        self._load_default_configs()
    
    def _load_default_configs(self):
        """Load default expert configurations."""
        
        # Security Analyst Expert
        self.configs[ExpertType.SECURITY_ANALYST] = ExpertConfig(
            expert_type=ExpertType.SECURITY_ANALYST,
            endpoint_url=os.getenv("LIGHTHOUSE_SECURITY_EXPERT_URL", "https://api.anthropic.com/v1/messages"),
            api_key=os.getenv("LIGHTHOUSE_SECURITY_EXPERT_KEY"),
            model_name="claude-3-sonnet-20240229",
            max_tokens=2048,
            temperature=0.1,  # Low temperature for security analysis
            timeout_seconds=30,
            retry_attempts=3,
            rate_limit_per_minute=60,
            system_prompt="""You are a cybersecurity expert specializing in threat analysis, vulnerability assessment, and security architecture review. 

Your role is to:
1. Analyze potential security threats and vulnerabilities
2. Assess risk levels and impact
3. Provide specific, actionable security recommendations
4. Review code and system designs for security issues
5. Identify attack vectors and mitigation strategies

Always provide:
- Clear, specific analysis
- Confidence level (0.0-1.0)
- Detailed reasoning
- Prioritized recommendations
- Risk assessment

Be thorough but concise. Focus on actionable insights."""
        )
        
        # Code Reviewer Expert
        self.configs[ExpertType.CODE_REVIEWER] = ExpertConfig(
            expert_type=ExpertType.CODE_REVIEWER,
            endpoint_url=os.getenv("LIGHTHOUSE_CODE_EXPERT_URL", "https://api.anthropic.com/v1/messages"),
            api_key=os.getenv("LIGHTHOUSE_CODE_EXPERT_KEY"),
            model_name="claude-3-sonnet-20240229",
            max_tokens=3072,
            temperature=0.2,
            timeout_seconds=45,
            retry_attempts=3,
            rate_limit_per_minute=40,
            system_prompt="""You are a senior software engineer and code review expert with deep expertise in software architecture, best practices, and code quality.

Your role is to:
1. Review code for bugs, performance issues, and maintainability
2. Assess architecture and design patterns
3. Identify potential improvements and optimizations
4. Check adherence to coding standards and best practices
5. Evaluate security implications of code changes

Always provide:
- Detailed code analysis
- Specific improvement suggestions
- Confidence in your assessment
- Reasoning for recommendations
- Priority levels for issues found

Be constructive and specific in your feedback."""
        )
        
        # Architecture Validator Expert
        self.configs[ExpertType.ARCHITECTURE_VALIDATOR] = ExpertConfig(
            expert_type=ExpertType.ARCHITECTURE_VALIDATOR,
            endpoint_url=os.getenv("LIGHTHOUSE_ARCH_EXPERT_URL", "https://api.anthropic.com/v1/messages"),
            api_key=os.getenv("LIGHTHOUSE_ARCH_EXPERT_KEY"),
            model_name="claude-3-sonnet-20240229",
            max_tokens=4096,
            temperature=0.1,
            timeout_seconds=60,
            retry_attempts=3,
            rate_limit_per_minute=30,
            system_prompt="""You are a senior software architect and systems design expert with expertise in distributed systems, scalability, and architectural patterns.

Your role is to:
1. Validate system architecture and design decisions
2. Assess scalability, reliability, and maintainability
3. Review integration patterns and data flows
4. Identify architectural risks and bottlenecks
5. Recommend improvements and alternatives

Always provide:
- Comprehensive architectural analysis
- Risk assessment
- Scalability considerations
- Integration recommendations
- Confidence level and reasoning

Focus on long-term sustainability and best practices."""
        )
    
    def configure_expert(self, expert_config: ExpertConfig):
        """Configure an expert service."""
        self.configs[expert_config.expert_type] = expert_config
        logger.info(f"Configured expert: {expert_config.expert_type.value}")
    
    async def query_expert(self, 
                          expert_type: ExpertType,
                          query_text: str,
                          context: Optional[Dict[str, Any]] = None,
                          priority: QueryPriority = QueryPriority.NORMAL,
                          timeout_seconds: Optional[int] = None) -> ExpertResponse:
        """
        Query an expert LLM service.
        
        Args:
            expert_type: Type of expert to query
            query_text: The query text
            context: Additional context for the query
            priority: Query priority
            timeout_seconds: Override default timeout
            
        Returns:
            Expert response
        """
        if expert_type not in self.configs:
            raise ValueError(f"No configuration found for expert type: {expert_type.value}")
        
        config = self.configs[expert_type]
        if not config.enabled:
            raise ValueError(f"Expert type {expert_type.value} is disabled")
        
        # Create query
        query_id = hashlib.md5(f"{expert_type.value}_{query_text}_{time.time()}".encode()).hexdigest()[:16]
        
        query = ExpertQuery(
            query_id=query_id,
            expert_type=expert_type,
            query_text=query_text,
            context=context or {},
            priority=priority,
            timeout_seconds=timeout_seconds or config.timeout_seconds,
            created_at=datetime.utcnow()
        )
        
        logger.info(f"Querying expert {expert_type.value} with query {query_id}")
        
        # Select provider based on config
        provider_name = self._select_provider(config)
        provider = self.providers[provider_name]
        
        try:
            query.status = QueryStatus.IN_PROGRESS
            self.active_queries[query_id] = query
            
            # Execute query
            response = await provider.query_expert(query, config)
            
            # Store response
            query.status = QueryStatus.COMPLETED
            self.completed_queries[query_id] = response
            
            logger.info(f"Expert query {query_id} completed successfully")
            return response
            
        except Exception as e:
            query.status = QueryStatus.FAILED
            query.error_message = str(e)
            logger.error(f"Expert query {query_id} failed: {str(e)}")
            raise
        
        finally:
            # Clean up active query
            self.active_queries.pop(query_id, None)
    
    def _select_provider(self, config: ExpertConfig) -> str:
        """Select appropriate provider based on configuration."""
        if "anthropic" in config.endpoint_url:
            return "anthropic"
        elif "openai" in config.endpoint_url:
            return "openai"
        else:
            # Default to Anthropic
            return "anthropic"
    
    async def health_check(self, expert_type: Optional[ExpertType] = None) -> Dict[str, bool]:
        """
        Check health of expert services.
        
        Args:
            expert_type: Specific expert to check, or all if None
            
        Returns:
            Health status for each expert
        """
        results = {}
        
        experts_to_check = [expert_type] if expert_type else list(self.configs.keys())
        
        for expert in experts_to_check:
            if expert in self.configs:
                config = self.configs[expert]
                provider_name = self._select_provider(config)
                provider = self.providers[provider_name]
                
                try:
                    is_healthy = await provider.health_check(config)
                    results[expert.value] = is_healthy
                except Exception as e:
                    logger.error(f"Health check failed for {expert.value}: {str(e)}")
                    results[expert.value] = False
            else:
                results[expert.value] = False
        
        return results
    
    async def get_query_status(self, query_id: str) -> Optional[QueryStatus]:
        """Get status of a query."""
        if query_id in self.active_queries:
            return self.active_queries[query_id].status
        elif query_id in self.completed_queries:
            return QueryStatus.COMPLETED
        else:
            return None
    
    async def get_response(self, query_id: str) -> Optional[ExpertResponse]:
        """Get response for a completed query."""
        return self.completed_queries.get(query_id)
    
    def get_expert_types(self) -> List[ExpertType]:
        """Get list of available expert types."""
        return list(self.configs.keys())
    
    def get_expert_config(self, expert_type: ExpertType) -> Optional[ExpertConfig]:
        """Get configuration for an expert type."""
        return self.configs.get(expert_type)
    
    async def close(self):
        """Close all provider connections."""
        for provider in self.providers.values():
            await provider.close()


# Global expert client instance
_global_expert_client: Optional[ExpertLLMClient] = None


def get_expert_llm_client() -> ExpertLLMClient:
    """Get global expert LLM client instance."""
    global _global_expert_client
    if _global_expert_client is None:
        _global_expert_client = ExpertLLMClient()
    return _global_expert_client


async def query_security_expert(query_text: str, context: Optional[Dict[str, Any]] = None) -> ExpertResponse:
    """Convenience function to query security expert."""
    client = get_expert_llm_client()
    return await client.query_expert(ExpertType.SECURITY_ANALYST, query_text, context)


async def query_code_expert(query_text: str, context: Optional[Dict[str, Any]] = None) -> ExpertResponse:
    """Convenience function to query code review expert."""
    client = get_expert_llm_client()
    return await client.query_expert(ExpertType.CODE_REVIEWER, query_text, context)


async def query_architecture_expert(query_text: str, context: Optional[Dict[str, Any]] = None) -> ExpertResponse:
    """Convenience function to query architecture expert."""
    client = get_expert_llm_client()
    return await client.query_expert(ExpertType.ARCHITECTURE_VALIDATOR, query_text, context)