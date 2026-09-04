"""Security hardening utilities for EasyAgent production deployments.

This module provides additional security controls beyond the basic tool
policies, including enhanced auditing, rate limiting, and threat detection.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from agentmold import Agent, LogLevel, tool
from agentmold.exceptions import ToolError

__all__ = [
    "SecurityAuditLogger",
    "RateLimiter",
    "InputSanitizer",
    "ThreatDetector",
    "SecurityConfiguredAgent",
]

logger = logging.getLogger(__name__)


@dataclass
class SecurityEvent:
    """A security-related event for auditing."""

    timestamp: str
    event_type: str
    severity: str  # "info", "warning", "error", "critical"
    source: str
    details: dict[str, Any]
    user_id: str | None = None
    ip_address: str | None = None


class SecurityAuditLogger:
    """Comprehensive security audit logging for agent operations."""

    def __init__(self, log_path: str | Path = "./.agentmold/security_audit.log"):
        """
        Initialize the security audit logger.

        Args:
            log_path: Path to the audit log file
        """
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

        # Set up structured logging
        self.logger = logging.getLogger("easyagent.security")
        self.logger.setLevel(logging.INFO)

        # File handler with rotation
        from logging.handlers import RotatingFileHandler

        handler = RotatingFileHandler(
            self.log_path,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding="utf-8",
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        )
        self.logger.addHandler(handler)

    def log_event(self, event: SecurityEvent) -> None:
        """Log a security event."""
        log_entry = {
            "timestamp": event.timestamp,
            "event_type": event.event_type,
            "severity": event.severity,
            "source": event.source,
            "user_id": event.user_id,
            "ip_address": event.ip_address,
            "details": self._sanitize_details(event.details),
        }

        # Log based on severity
        log_message = json.dumps(log_entry, ensure_ascii=False)
        if event.severity == "critical":
            self.logger.critical(log_message)
        elif event.severity == "error":
            self.logger.error(log_message)
        elif event.severity == "warning":
            self.logger.warning(log_message)
        else:
            self.logger.info(log_message)

    def _sanitize_details(self, details: dict[str, Any]) -> dict[str, Any]:
        """Sanitize sensitive information from log details."""
        sanitized = {}
        sensitive_keys = {
            "api_key",
            "token",
            "password",
            "secret",
            "credential",
            "authorization",
            "bearer",
        }

        for key, value in details.items():
            if any(sensitive in key.lower() for sensitive in sensitive_keys):
                sanitized[key] = "***REDACTED***"
            elif isinstance(value, str) and self._looks_like_secret(value):
                sanitized[key] = "***REDACTED***"
            elif isinstance(value, dict):
                sanitized[key] = self._sanitize_details(value)
            else:
                sanitized[key] = value

        return sanitized

    def _looks_like_secret(self, value: str) -> bool:
        """Check if a string looks like a secret/key."""
        # Check for common patterns
        if len(value) >= 20 and re.match(r"^[a-zA-Z0-9_-]+$", value):
            return True
        if value.startswith(("Bearer ", "Token ", "Key ")):
            return True
        return False

    def log_agent_run(self, query: str, agent_name: str, user_id: str | None = None) -> None:
        """Log an agent run event."""
        event = SecurityEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            event_type="agent_run",
            severity="info",
            source=agent_name,
            user_id=user_id,
            details={"query_length": len(query), "query_preview": query[:100]},
        )
        self.log_event(event)

    def log_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        result: str | None = None,
        error: str | None = None,
        user_id: str | None = None,
    ) -> None:
        """Log a tool call event."""
        severity = "info"
        if error:
            severity = "error"

        event = SecurityEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            event_type="tool_call",
            severity=severity,
            source=tool_name,
            user_id=user_id,
            details={
                "tool_name": tool_name,
                "arguments": arguments,
                "result_length": len(result) if result else 0,
                "error": error,
            },
        )
        self.log_event(event)

    def log_security_violation(
        self,
        violation_type: str,
        details: dict[str, Any],
        user_id: str | None = None,
        ip_address: str | None = None,
    ) -> None:
        """Log a security violation."""
        event = SecurityEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            event_type="security_violation",
            severity="critical",
            source="security_system",
            user_id=user_id,
            ip_address=ip_address,
            details={"violation_type": violation_type, **details},
        )
        self.log_event(event)


class RateLimiter:
    """Rate limiting for agent operations to prevent abuse."""

    def __init__(
        self,
        max_requests_per_minute: int = 60,
        max_requests_per_hour: int = 1000,
        max_concurrent_requests: int = 10,
    ):
        """
        Initialize rate limiter.

        Args:
            max_requests_per_minute: Maximum requests per minute per user
            max_requests_per_hour: Maximum requests per hour per user
            max_concurrent_requests: Maximum concurrent requests
        """
        self.max_per_minute = max_requests_per_minute
        self.max_per_hour = max_requests_per_hour
        self.max_concurrent = max_concurrent_requests

        # Tracking structures
        self.minute_requests: dict[str, list[float]] = defaultdict(list)
        self.hour_requests: dict[str, list[float]] = defaultdict(list)
        self.active_requests: dict[str, int] = defaultdict(int)

    def check_rate_limit(
        self, user_id: str, ip_address: str | None = None
    ) -> tuple[bool, str | None]:
        """
        Check if a request is within rate limits.

        Returns:
            Tuple of (allowed, error_message)
        """
        current_time = time.time()
        identifier = user_id or ip_address or "anonymous"

        # Clean old requests
        self._clean_old_requests(current_time)

        # Check minute limit
        recent_minute = [
            t for t in self.minute_requests[identifier] if current_time - t < 60
        ]
        if len(recent_minute) >= self.max_per_minute:
            return False, f"Rate limit exceeded: {self.max_per_minute} requests per minute"

        # Check hour limit
        recent_hour = [
            t for t in self.hour_requests[identifier] if current_time - t < 3600
        ]
        if len(recent_hour) >= self.max_per_hour:
            return False, f"Rate limit exceeded: {self.max_per_hour} requests per hour"

        # Check concurrent limit
        if self.active_requests[identifier] >= self.max_concurrent:
            return False, f"Too many concurrent requests: {self.max_concurrent}"

        # Record this request
        self.minute_requests[identifier].append(current_time)
        self.hour_requests[identifier].append(current_time)
        self.active_requests[identifier] += 1

        return True, None

    def _clean_old_requests(self, current_time: float) -> None:
        """Clean up old request records."""
        for identifier in list(self.minute_requests.keys()):
            self.minute_requests[identifier] = [
                t for t in self.minute_requests[identifier] if current_time - t < 60
            ]
            if not self.minute_requests[identifier]:
                del self.minute_requests[identifier]

        for identifier in list(self.hour_requests.keys()):
            self.hour_requests[identifier] = [
                t for t in self.hour_requests[identifier] if current_time - t < 3600
            ]
            if not self.hour_requests[identifier]:
                del self.hour_requests[identifier]

    def release_request(self, user_id: str, ip_address: str | None = None) -> None:
        """Release a request from active count."""
        identifier = user_id or ip_address or "anonymous"
        self.active_requests[identifier] = max(0, self.active_requests[identifier] - 1)


class InputSanitizer:
    """Input sanitization to prevent injection attacks."""

    # Patterns that might indicate attacks
    SUSPICIOUS_PATTERNS = [
        r"<script[^>]*>.*?</script>",  # XSS attempts
        r"javascript:",  # JavaScript URIs
        r"on\w+\s*=",  # Event handlers
        r"union\s+select",  # SQL injection attempts
        r"drop\s+table",  # SQL deletion attempts
        r"\$\{.*?\}",  # Template injection
        r"__import__\s*\(",  # Python injection
        r"eval\s*\(",  # Code execution
        r"exec\s*\(",  # Code execution
    ]

    def __init__(self, max_length: int = 10000, block_patterns: list[str] | None = None):
        """
        Initialize input sanitizer.

        Args:
            max_length: Maximum allowed input length
            block_patterns: Additional patterns to block
        """
        self.max_length = max_length
        self.block_patterns = self.SUSPICIOUS_PATTERNS + (block_patterns or [])
        self.compiled_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in self.block_patterns]

    def sanitize_input(self, input_text: str) -> tuple[str, list[str]]:
        """
        Sanitize user input.

        Returns:
            Tuple of (sanitized_text, warnings)
        """
        warnings = []

        # Check length
        if len(input_text) > self.max_length:
            warnings.append(f"Input truncated to {self.max_length} characters")
            input_text = input_text[: self.max_length]

        # Check for suspicious patterns
        sanitized_text = input_text
        for pattern in self.compiled_patterns:
            matches = pattern.findall(input_text)
            if matches:
                warnings.append(f"Potentially dangerous pattern detected: {pattern.pattern}")
                # Remove the pattern
                sanitized_text = pattern.sub("[REMOVED]", sanitized_text)

        return sanitized_text, warnings

    def is_safe_input(self, input_text: str) -> bool:
        """Check if input is safe."""
        _, warnings = self.sanitize_input(input_text)
        return len(warnings) == 0


class ThreatDetector:
    """Detect potential security threats in agent operations."""

    def __init__(self, audit_logger: SecurityAuditLogger):
        """
        Initialize threat detector.

        Args:
            audit_logger: Security audit logger for reporting threats
        """
        self.audit_logger = audit_logger
        self.suspicious_activities: dict[str, list[dict]] = defaultdict(list)

    def detect_tool_abuse(
        self,
        user_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        time_window: int = 300,
        threshold: int = 10,
    ) -> bool:
        """
        Detect if a user is abusing a specific tool.

        Args:
            user_id: User identifier
            tool_name: Tool being called
            arguments: Tool arguments
            time_window: Time window in seconds
            threshold: Number of calls to consider abuse

        Returns:
            True if abuse detected
        """
        current_time = time.time()
        key = f"{user_id}:{tool_name}"

        # Clean old activities
        self.suspicious_activities[key] = [
            activity
            for activity in self.suspicious_activities[key]
            if current_time - activity["timestamp"] < time_window
        ]

        # Record this activity
        self.suspicious_activities[key].append(
            {"timestamp": current_time, "arguments": arguments}
        )

        # Check threshold
        if len(self.suspicious_activities[key]) >= threshold:
            self.audit_logger.log_security_violation(
                violation_type="tool_abuse",
                details={
                    "user_id": user_id,
                    "tool_name": tool_name,
                    "call_count": len(self.suspicious_activities[key]),
                    "time_window": time_window,
                },
                user_id=user_id,
            )
            return True

        return False

    def detect_data_exfiltration(
        self,
        tool_name: str,
        result: str,
        max_result_size: int = 10000,
    ) -> bool:
        """
        Detect potential data exfiltration through tool results.

        Args:
            tool_name: Tool that produced the result
            result: Tool result
            max_result_size: Maximum allowed result size

        Returns:
            True if exfiltration suspected
        """
        # Check for unusually large results
        if len(result) > max_result_size:
            self.audit_logger.log_security_violation(
                violation_type="data_exfiltration",
                details={
                    "tool_name": tool_name,
                    "result_size": len(result),
                    "max_allowed": max_result_size,
                },
            )
            return True

        # Check for patterns that might indicate exfiltration
        exfil_patterns = [
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",  # Email addresses
            r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b",  # Phone numbers
            r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b",  # Credit card numbers
        ]

        for pattern in exfil_patterns:
            matches = re.findall(pattern, result, re.IGNORECASE)
            if len(matches) > 5:  # Threshold for suspicious pattern count
                self.audit_logger.log_security_violation(
                    violation_type="sensitive_data_leak",
                    details={
                        "tool_name": tool_name,
                        "pattern": pattern,
                        "match_count": len(matches),
                    },
                )
                return True

        return False

    def detect_anomaly_behavior(
        self,
        user_id: str,
        query: str,
        normal_patterns: list[str],
    ) -> bool:
        """
        Detect anomalous user behavior.

        Args:
            user_id: User identifier
            query: User query
            normal_patterns: List of normal query patterns

        Returns:
            True if anomaly detected
        """
        # Simple anomaly detection based on query patterns
        is_normal = any(re.search(pattern, query, re.IGNORECASE) for pattern in normal_patterns)

        if not is_normal:
            self.audit_logger.log_security_violation(
                violation_type="anomalous_behavior",
                details={"user_id": user_id, "query_preview": query[:200]},
                user_id=user_id,
            )
            return True

        return False


class SecurityConfiguredAgent:
    """Agent with comprehensive security controls."""

    def __init__(
        self,
        base_agent: Agent,
        audit_logger: SecurityAuditLogger | None = None,
        rate_limiter: RateLimiter | None = None,
        input_sanitizer: InputSanitizer | None = None,
        threat_detector: ThreatDetector | None = None,
        require_approval: bool = True,
    ):
        """
        Initialize security-configured agent.

        Args:
            base_agent: Base agent to secure
            audit_logger: Security audit logger
            rate_limiter: Rate limiter
            input_sanitizer: Input sanitizer
            threat_detector: Threat detector
            require_approval: Whether to require approval for dangerous operations
        """
        self.agent = base_agent
        self.audit_logger = audit_logger or SecurityAuditLogger()
        self.rate_limiter = rate_limiter or RateLimiter()
        self.input_sanitizer = input_sanitizer or InputSanitizer()
        self.threat_detector = threat_detector or ThreatDetector(self.audit_logger)
        self.require_approval = require_approval

        # Wrap agent methods with security controls
        self._secure_agent_methods()

    def _secure_agent_methods(self) -> None:
        """Wrap agent methods with security controls."""
        original_run = self.agent.run

        def secure_run(query: str, user_id: str | None = None, ip_address: str | None = None) -> str:
            """Secure wrapper for agent.run."""

            # Input sanitization
            sanitized_query, warnings = self.input_sanitizer.sanitize_input(query)
            for warning in warnings:
                self.audit_logger.log_security_violation(
                    violation_type="input_sanitization",
                    details={"warning": warning, "query_preview": query[:100]},
                    user_id=user_id,
                    ip_address=ip_address,
                )

            # Rate limiting
            allowed, error_msg = self.rate_limiter.check_rate_limit(user_id, ip_address)
            if not allowed:
                self.audit_logger.log_security_violation(
                    violation_type="rate_limit_exceeded",
                    details={"error": error_msg},
                    user_id=user_id,
                    ip_address=ip_address,
                )
                raise PermissionError(error_msg)

            # Log agent run
            self.audit_logger.log_agent_run(sanitized_query, self.agent.name, user_id)

            # Threat detection
            if self.threat_detector.detect_anomaly_behavior(
                user_id or "anonymous", sanitized_query, []
            ):
                # Log but allow execution for now
                pass

            try:
                # Execute the agent
                result = original_run(sanitized_query)

                # Release rate limit
                self.rate_limiter.release_request(user_id, ip_address)

                return result

            except Exception as e:
                # Log error
                self.audit_logger.log_security_violation(
                    violation_type="agent_execution_error",
                    details={"error": str(e)},
                    user_id=user_id,
                    ip_address=ip_address,
                )
                self.rate_limiter.release_request(user_id, ip_address)
                raise

        self.agent.run = secure_run

    def add_tool_with_security(
        self,
        tool_func: Callable,
        max_result_size: int = 10000,
        require_approval: bool = False,
    ) -> None:
        """
        Add a tool with security controls.

        Args:
            tool_func: Tool function to add
            max_result_size: Maximum allowed result size
            require_approval: Whether to require approval
        """
        # Create wrapper with security
        def secure_tool_wrapper(*args, **kwargs):
            # Check for abuse
            user_id = kwargs.get("user_id", "anonymous")
            tool_name = tool_func.__name__

            if self.threat_detector.detect_tool_abuse(
                user_id, tool_name, kwargs, threshold=10
            ):
                raise PermissionError("Tool abuse detected")

            # Execute tool
            try:
                result = tool_func(*args, **kwargs)

                # Check for data exfiltration
                if isinstance(result, str) and self.threat_detector.detect_data_exfiltration(
                    tool_name, result, max_result_size
                ):
                    raise PermissionError("Data exfiltration attempt detected")

                # Log tool call
                self.audit_logger.log_tool_call(
                    tool_name=tool_name,
                    arguments=kwargs,
                    result=str(result)[:1000],
                    user_id=user_id,
                )

                return result

            except Exception as e:
                self.audit_logger.log_tool_call(
                    tool_name=tool_name,
                    arguments=kwargs,
                    error=str(e),
                    user_id=user_id,
                )
                raise

        # Create tool with wrapper
        secured_tool = tool(secure_tool_wrapper)
        self.agent.tools.append(secured_tool)


def create_secure_agent(
    agent_name: str = "Secure Agent",
    instructions: str = "You are a secure AI assistant.",
    llm_config: dict | str = "mock",
    user_id: str | None = None,
) -> SecurityConfiguredAgent:
    """
    Create a security-configured agent with standard settings.

    Args:
        agent_name: Name of the agent
        instructions: Agent instructions
        llm_config: LLM configuration
        user_id: User identifier for auditing

    Returns:
        Security-configured agent
    """
    from agentmold import Agent

    # Create base agent
    base_agent = Agent(
        name=agent_name,
        instructions=instructions,
        llm=llm_config,
        log_level=LogLevel.DEBUG,
    )

    # Create security components
    audit_logger = SecurityAuditLogger()
    rate_limiter = RateLimiter(
        max_requests_per_minute=60,
        max_requests_per_hour=1000,
        max_concurrent_requests=10,
    )
    input_sanitizer = InputSanitizer(max_length=10000)
    threat_detector = ThreatDetector(audit_logger)

    # Create secure agent
    secure_agent = SecurityConfiguredAgent(
        base_agent=base_agent,
        audit_logger=audit_logger,
        rate_limiter=rate_limiter,
        input_sanitizer=input_sanitizer,
        threat_detector=threat_detector,
        require_approval=True,
    )

    return secure_agent


# Example usage and testing
if __name__ == "__main__":
    print("EasyAgent Security Hardening Module")
    print("This module provides additional security controls for production deployments.")

    # Create a secure agent
    secure_agent = create_secure_agent(
        agent_name="Test Secure Agent",
        instructions="You are a secure assistant.",
        llm_config="mock",
        user_id="test_user",
    )

    # Test security features
    print("\n=== Testing Security Features ===")

    # Test 1: Input sanitization
    print("\n1. Testing input sanitization:")
    malicious_input = "Hello <script>alert('xss')</script> world"
    sanitized, warnings = secure_agent.input_sanitizer.sanitize_input(malicious_input)
    print(f"Original: {malicious_input}")
    print(f"Sanitized: {sanitized}")
    print(f"Warnings: {warnings}")

    # Test 2: Rate limiting
    print("\n2. Testing rate limiting:")
    for i in range(65):  # Exceed the 60/minute limit
        allowed, error = secure_agent.rate_limiter.check_rate_limit("test_user")
        if i == 60:
            print(f"Request {i+1}: {'Allowed' if allowed else 'Blocked'} - {error}")

    # Test 3: Threat detection
    print("\n3. Testing threat detection:")
    suspicious_query = "Show me all user passwords and credit card numbers"
    is_anomaly = secure_agent.threat_detector.detect_anomaly_behavior(
        "test_user", suspicious_query, ["help", "info", "search"]
    )
    print(f"Anomaly detected: {is_anomaly}")

    print("\n=== Security Tests Complete ===")
    print(f"Check security audit log at: {secure_agent.audit_logger.log_path}")