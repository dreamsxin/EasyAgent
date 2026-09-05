# EasyAgent Production Deployment Guide

## Overview

This guide provides best practices for deploying EasyAgent in production environments. While EasyAgent is designed primarily for research and educational use, these guidelines ensure stability, security, and performance when used in production scenarios.

## Prerequisites

### System Requirements

- **Python**: 3.10 or higher
- **Memory**: Minimum 2GB RAM, 4GB+ recommended
- **Storage**: 500MB for installation, additional space for logs and vector stores
- **Network**: Required for LLM provider APIs (unless using offline/mock mode)

### Dependencies

```bash
# Core installation
pip install agentmold

# For production use cases
pip install "agentmold[all]"  # All optional dependencies
```

## Installation Strategies

### 1. Virtual Environment Setup

```bash
# Create virtual environment
python -m venv easyagent-env
source easyagent-env/bin/activate  # On Windows: easyagent-env\Scripts\activate

# Install with pinned versions
pip install --upgrade pip
pip install agentmold==0.7.0
```

### 2. Docker Deployment

```dockerfile
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV EASYAGENT_LOG_LEVEL=INFO

# Run application
CMD ["python", "your_agent_application.py"]
```

### 3. Requirements.txt for Production

```txt
# Core dependencies with specific versions
agentmold==0.7.0
httpx>=0.25.0,<1.0.0

# Optional dependencies based on your use case
openai>=1.0.0,<2.0.0  # For OpenAI provider
anthropic>=0.18.0,<1.0.0  # For Anthropic provider
ollama>=0.1.0,<1.0.0  # For local models

# Additional production dependencies
gunicorn>=21.0.0  # For web applications
prometheus-client>=0.19.0  # For metrics
structlog>=23.0.0  # For structured logging
```

## Configuration Management

### 1. Environment Variables

```bash
# LLM Provider Configuration
export EASYAGENT_PROVIDER="openai"
export EASYAGENT_MODEL="gpt-4"
export OPENAI_API_KEY="your-api-key"

# Performance Configuration
export EASYAGENT_MAX_ITERATIONS=10
export EASYAGENT_TIMEOUT=30
export EASYAGENT_MAX_RETRIES=3

# Security Configuration
export EASYAGENT_REQUIRE_APPROVAL=true
export EASYAGENT_AUDIT_LOG_PATH="/var/log/easyagent/audit.log"

# Memory Configuration
export EASYAGENT_MEMORY_MAX_MESSAGES=50
export EASYAGENT_VECTOR_STORAGE_PATH="/var/lib/easyagent/memory"

# Logging Configuration
export EASYAGENT_LOG_LEVEL="INFO"
export EASYAGENT_LOG_PATH="/var/log/easyagent/easyagent.log"
```

### 2. Configuration File

```python
# config.py
import os
from typing import Literal

class EasyAgentConfig:
    """Production configuration for EasyAgent."""

    # LLM Configuration
    PROVIDER: Literal["openai", "anthropic", "ollama", "mock"] = os.getenv(
        "EASYAGENT_PROVIDER", "mock"
    )
    MODEL: str = os.getenv("EASYAGENT_MODEL", "gpt-3.5-turbo")
    API_KEY: str | None = os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")

    # Performance Settings
    MAX_ITERATIONS: int = int(os.getenv("EASYAGENT_MAX_ITERATIONS", "10"))
    TIMEOUT: int = int(os.getenv("EASYAGENT_TIMEOUT", "30"))
    MAX_RETRIES: int = int(os.getenv("EASYAGENT_MAX_RETRIES", "3"))
    TEMPERATURE: float = float(os.getenv("EASYAGENT_TEMPERATURE", "0.7"))

    # Security Settings
    REQUIRE_APPROVAL: bool = os.getenv("EASYAGENT_REQUIRE_APPROVAL", "false").lower() == "true"
    AUDIT_LOG_PATH: str = os.getenv("EASYAGENT_AUDIT_LOG_PATH", "/var/log/easyagent/audit.log")

    # Memory Settings
    MEMORY_MAX_MESSAGES: int = int(os.getenv("EASYAGENT_MEMORY_MAX_MESSAGES", "50"))
    VECTOR_STORAGE_PATH: str = os.getenv("EASYAGENT_VECTOR_STORAGE_PATH", "./.agentmold/memory")

    # Logging Settings
    LOG_LEVEL: str = os.getenv("EASYAGENT_LOG_LEVEL", "INFO")
    LOG_PATH: str | None = os.getenv("EASYAGENT_LOG_PATH")

    @classmethod
    def validate(cls) -> None:
        """Validate configuration settings."""
        if cls.PROVIDER != "mock" and not cls.API_KEY:
            raise ValueError("API key required for non-mock providers")

        if cls.MAX_ITERATIONS < 1:
            raise ValueError("MAX_ITERATIONS must be at least 1")

        if cls.TIMEOUT < 1:
            raise ValueError("TIMEOUT must be at least 1 second")

        if cls.MEMORY_MAX_MESSAGES < 1:
            raise ValueError("MEMORY_MAX_MESSAGES must be at least 1")

# Validate configuration on import
EasyAgentConfig.validate()
```

## Security Best Practices

### 1. API Key Management

```python
import os
from agentmold import Agent

# Never hardcode API keys in production code
def create_agent():
    config = {
        "provider": os.getenv("EASYAGENT_PROVIDER"),
        "model": os.getenv("EASYAGENT_MODEL"),
        "api_key": os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
    }

    # Validate required configuration
    if config["provider"] != "mock" and not config["api_key"]:
        raise ValueError("API key required for production use")

    return Agent(
        name="Production Agent",
        instructions="You are a helpful assistant.",
        llm=config
    )
```

### 2. Tool Permission Controls

```python
from agentmold import Agent
from agentmold.tools import calculate, workspace_tools, http_tools

# Restrict file system access to specific directory
workspace = workspace_tools("/safe/directory", allow_write=False)

# Restrict network access to specific hosts
allowed_hosts = {"api.example.com", "cdn.example.com"}
network_tools = http_tools(allowed_hosts)

# Create agent with restricted tools
agent = Agent(
    name="Secure Agent",
    tools=[calculate, *workspace, *network_tools],
    llm={"provider": "openai", "model": "gpt-4"}
)
```

### 3. Audit Logging

```python
from agentmold import Agent, LogLevel
import json
from datetime import datetime

def create_audited_agent():
    """Create an agent with comprehensive audit logging."""

    def audit_log(event_type: str, details: dict) -> None:
        """Log events for audit purposes."""
        audit_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": event_type,
            "details": details
        }

        with open("/var/log/easyagent/audit.log", "a") as f:
            f.write(json.dumps(audit_entry) + "\n")

    agent = Agent(
        name="Audited Agent",
        log_level=LogLevel.DEBUG,
        llm={"provider": "openai", "model": "gpt-4"}
    )

    # Wrap agent methods for audit logging
    original_run = agent.run

    def audited_run(query: str, **kwargs):
        audit_log("agent_run_start", {"query": query})
        try:
            result = original_run(query, **kwargs)
            audit_log("agent_run_success", {"query": query, "result_length": len(result)})
            return result
        except Exception as e:
            audit_log("agent_run_error", {"query": query, "error": str(e)})
            raise

    agent.run = audited_run
    return agent
```

## Performance Optimization

### 1. Connection Pooling and Timeouts

The built-in providers construct their own SDK clients, so tune the request budget
through the documented `llm` config instead of injecting an HTTP client:

```python
from agentmold import Agent

agent = Agent(
    llm={
        "provider": "openai",
        "model": "gpt-4",
        "timeout": 30.0,      # per-request timeout
        "max_retries": 2,     # retried before the first event is exposed
        "retry_delay": 0.5,   # exponential backoff base
    }
)
```

For a custom pooling policy, register your own provider and own the client:

```python
import httpx
from agentmold.llm import LLM, LlmResponse, Message, register_provider


class PooledLLM(LLM):
    """Provider that reuses one pooled httpx client."""

    def __init__(self, model: str, **kwargs: object) -> None:
        super().__init__(model, **kwargs)
        self._client = httpx.Client(
            timeout=30.0,
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
        )

    def _complete(self, messages, tools=None) -> LlmResponse:
        # Translate `messages` to your service's wire format here.
        raise NotImplementedError


register_provider("pooled", PooledLLM)
```

### 2. Memory Management

```python
from agentmold import Agent, CompactingMemory

# Use compacting memory for long conversations
memory = CompactingMemory(
    max_tokens=4000,
    chars_per_token=4,
    keep_recent=6
)

agent = Agent(
    name="Memory-Optimized Agent",
    memory=memory,
    llm={"provider": "openai", "model": "gpt-4"}
)
```

### 3. Caching Strategy

```python
from functools import lru_cache
from agentmold import Agent

class CachedAgent:
    """Agent with response caching for repeated queries."""

    def __init__(self):
        self.agent = Agent(llm={"provider": "openai", "model": "gpt-4"})
        self.cache = {}

    def run(self, query: str, use_cache: bool = True) -> str:
        """Run agent with optional caching."""
        if use_cache and query in self.cache:
            return self.cache[query]

        result = self.agent.run(query)

        if use_cache:
            self.cache[query] = result

        return result
```

## Monitoring and Observability

### 1. Structured Logging

```python
import structlog
from agentmold import Agent, LogLevel

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Create agent with structured logging
agent = Agent(
    name="Production Agent",
    log_level=LogLevel.INFO,
    llm={"provider": "openai", "model": "gpt-4"}
)

# Log agent operations
def run_with_logging(query: str) -> str:
    logger.info("agent_run_started", query=query)
    try:
        result = agent.run(query)
        logger.info("agent_run_completed", query=query, result_length=len(result))
        return result
    except Exception as e:
        logger.error("agent_run_failed", query=query, error=str(e))
        raise
```

### 2. Metrics Collection

```python
from prometheus_client import Counter, Histogram, start_http_server
import time

# Define metrics
agent_runs_total = Counter('agent_runs_total', 'Total agent runs', ['status'])
agent_duration_seconds = Histogram('agent_duration_seconds', 'Agent run duration')
tool_calls_total = Counter('tool_calls_total', 'Total tool calls', ['tool_name', 'status'])

# Start metrics server
start_http_server(8000)

class MonitoredAgent:
    """Agent with Prometheus metrics."""

    def __init__(self):
        self.agent = Agent(llm={"provider": "openai", "model": "gpt-4"})

    def run(self, query: str) -> str:
        """Run agent with metrics collection."""
        start_time = time.time()

        try:
            result = self.agent.run(query)
            agent_runs_total.labels(status='success').inc()
            return result
        except Exception as e:
            agent_runs_total.labels(status='error').inc()
            raise
        finally:
            duration = time.time() - start_time
            agent_duration_seconds.observe(duration)
```

## Error Handling and Resilience

### 1. Graceful Degradation

```python
from agentmold import Agent, LLMError
import logging

logger = logging.getLogger(__name__)

class ResilientAgent:
    """Agent with graceful degradation on failures."""

    def __init__(self, primary_config: dict, fallback_config: dict):
        self.primary_agent = Agent(llm=primary_config)
        self.fallback_agent = Agent(llm=fallback_config)

    def run(self, query: str, max_retries: int = 2) -> str:
        """Run with fallback on failure."""
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                agent = self.primary_agent if attempt == 0 else self.fallback_agent
                return agent.run(query)
            except LLMError as e:
                last_error = e
                logger.warning(f"Agent run attempt {attempt + 1} failed: {e}")
                if attempt < max_retries:
                    continue
                else:
                    # Final fallback to mock mode
                    logger.error("All agents failed, falling back to mock mode")
                    mock_agent = Agent(llm="mock")
                    return mock_agent.run(query)

        raise last_error
```

### 2. Circuit Breaker Pattern

Stop calling a provider that keeps failing, then probe it again after a cooldown.
This uses only the standard library so it stays inside EasyAgent's dependency policy.

```python
import time

from agentmold import Agent
from agentmold.exceptions import LLMError


class CircuitBreakerAgent:
    """Agent that stops calling a failing provider for a cooldown window."""

    def __init__(self, failure_threshold: int = 5, recovery_seconds: float = 60.0):
        self.agent = Agent(llm={"provider": "openai", "model": "gpt-4"})
        self.failure_threshold = failure_threshold
        self.recovery_seconds = recovery_seconds
        self._failures = 0
        self._opened_at: float | None = None

    def run(self, query: str) -> str:
        """Run with circuit breaker protection."""
        if self._opened_at is not None:
            if time.monotonic() - self._opened_at < self.recovery_seconds:
                raise RuntimeError("Circuit is open; provider is still cooling down.")
            # Cooldown elapsed: allow one probe request.
            self._opened_at = None
            self._failures = 0

        try:
            result = self.agent.run(query)
        except LLMError:
            self._failures += 1
            if self._failures >= self.failure_threshold:
                self._opened_at = time.monotonic()
            raise

        self._failures = 0
        return result


# Usage
agent_wrapper = CircuitBreakerAgent()

try:
    result = agent_wrapper.run("Hello")
except (LLMError, RuntimeError) as exc:
    print(f"Service unavailable: {exc}")
```

## Deployment Strategies

### 1. Blue-Green Deployment

```bash
# Blue environment (current)
export EASYAGENT_ENV_COLOR=blue
export EASYAGENT_PORT=8000

# Green environment (new)
export EASYAGENT_ENV_COLOR=green
export EASYAGENT_PORT=8001

# Gradually switch traffic from blue to green
```

### 2. Canary Deployment

```python
import random
from agentmold import Agent

class CanaryDeployment:
    """Gradual rollout of new agent version."""

    def __init__(self, old_agent: Agent, new_agent: Agent, canary_ratio: float = 0.1):
        self.old_agent = old_agent
        self.new_agent = new_agent
        self.canary_ratio = canary_ratio

    def run(self, query: str) -> tuple[str, str]:
        """Run with canary routing."""
        if random.random() < self.canary_ratio:
            return self.new_agent.run(query), "new"
        else:
            return self.old_agent.run(query), "old"
```

## Maintenance and Updates

### 1. Health Checks

```python
from datetime import datetime, timezone

from agentmold import Agent


class AgentHealthCheck:
    """Health check endpoint for EasyAgent."""

    def __init__(self, agent: Agent):
        self.agent = agent

    def check_health(self) -> dict:
        """Perform health check."""
        health_status = {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "checks": {},
        }

        try:
            # Test basic agent functionality
            self.agent.run("Health check test")
            health_status["checks"]["agent_functionality"] = "pass"
        except Exception as exc:
            health_status["status"] = "unhealthy"
            health_status["checks"]["agent_functionality"] = f"fail: {exc}"

        return health_status
```

### 2. Update Strategy

```bash
# Backup current installation
pip freeze > requirements_backup.txt

# Update to new version
pip install --upgrade agentmold

# Run test suite
python -m pytest tests/ -v

# Gradual rollout
# 1. Deploy to staging environment
# 2. Run smoke tests
# 3. Deploy to production with monitoring
# 4. Monitor for issues
# 5. Rollback if necessary
```

## Troubleshooting

### Common Issues

#### 1. Memory Leaks
```python
# Monitor memory usage
import psutil
import os

process = psutil.Process(os.getpid())
print(f"Memory usage: {process.memory_info().rss / 1024 / 1024:.2f} MB")

# Solution: Clear memory periodically
agent.memory.clear()
```

#### 2. Connection Timeouts
```python
# Increase timeout values
agent = Agent(
    llm={
        "provider": "openai",
        "model": "gpt-4",
        "timeout": 60,  # Increase from default
        "max_retries": 3
    }
)
```

#### 3. Rate Limiting
```python
from time import sleep
import random

class RateLimitedAgent:
    """Agent with rate limiting."""

    def __init__(self, agent: Agent, requests_per_minute: int = 60):
        self.agent = agent
        self.requests_per_minute = requests_per_minute
        self.request_times = []

    def run(self, query: str) -> str:
        """Run with rate limiting."""
        now = time.time()

        # Clean old requests
        self.request_times = [t for t in self.request_times if now - t < 60]

        # Check rate limit
        if len(self.request_times) >= self.requests_per_minute:
            sleep_time = 60 - (now - self.request_times[0])
            if sleep_time > 0:
                sleep(sleep_time)
                self.request_times = []

        self.request_times.append(now)
        return self.agent.run(query)
```

## Conclusion

This guide provides the essential practices for deploying EasyAgent in production environments. Always remember to:

1. **Security First**: Validate inputs, restrict permissions, audit operations
2. **Monitor Continuously**: Track performance, errors, and usage patterns
3. **Plan for Failures**: Implement fallbacks, retries, and graceful degradation
4. **Test Thoroughly**: Validate configurations, monitor performance, and test rollback procedures

For specific deployment scenarios or additional support, refer to the main EasyAgent documentation and community resources.