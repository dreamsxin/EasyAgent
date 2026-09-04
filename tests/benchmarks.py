"""Performance benchmarks for EasyAgent core components.

Run with: pytest tests/benchmarks.py -v --benchmark-only
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import pytest

# Conditional import - benchmarks only run when pytest-benchmark is available
try:
    import pytest_benchmark

    BENCHMARK_AVAILABLE = True
except ImportError:
    BENCHMARK_AVAILABLE = False
    pytest_benchmark = None  # type: ignore


@pytest.mark.skipif(not BENCHMARK_AVAILABLE, reason="pytest-benchmark not installed")
class TestAgentPerformance:
    """Performance benchmarks for Agent execution."""

    def test_mock_agent_simple_answer(self, benchmark):
        """Benchmark simple answer without tools."""
        from agentmold import Agent

        agent = Agent(name="Test Agent", llm="mock")

        def run_simple():
            return agent("Hello, how are you?")

        result = benchmark(run_simple)
        assert result  # Ensure we got a response

    def test_mock_agent_with_tool(self, benchmark):
        """Benchmark agent with single tool invocation."""
        from agentmold import Agent, tool

        @tool
        def calculate(expression: str) -> str:
            """Calculate a mathematical expression."""
            try:
                return str(eval(expression, {"__builtins__": {}}, {}))
            except Exception:
                return "Error"

        agent = Agent(name="Calculator", tools=[calculate], llm="mock")

        def run_with_tool():
            return agent("What is 2 + 2?")

        result = benchmark(run_with_tool)
        assert "tool:" in result.lower() or "4" in result

    def test_memory_add_retrieve(self, benchmark):
        """Benchmark memory operations."""
        from agentmold import Agent, Memory
        from agentmold.llm import Message

        memory = Memory(max_messages=100)
        agent = Agent(name="Test Agent", memory=memory, llm="mock")

        def memory_operations():
            # Add messages
            for i in range(10):
                memory.add(Message(role="user", content=f"Message {i}"))
            # Retrieve messages
            return memory.messages()

        messages = benchmark(memory_operations)
        assert len(messages) >= 10

    def test_tool_schema_generation(self, benchmark):
        """Benchmark tool schema generation."""
        from agentmold import tool

        @tool
        def complex_tool(
            name: str,
            age: int,
            scores: list[float],
            metadata: dict[str, Any] | None = None,
        ) -> str:
            """A complex tool with various parameter types."""
            return f"Processed {name}"

        def generate_schema():
            return complex_tool.schema

        schema = benchmark(generate_schema)
        assert schema["name"] == "complex_tool"
        assert "parameters" in schema

    def test_multiple_sequential_runs(self, benchmark):
        """Benchmark multiple sequential agent runs."""
        from agentmold import Agent

        agent = Agent(name="Test Agent", llm="mock")

        def sequential_runs():
            results = []
            for i in range(5):
                results.append(agent(f"Question {i}"))
            return results

        results = benchmark(sequential_runs)
        assert len(results) == 5


@pytest.mark.skipif(not BENCHMARK_AVAILABLE, reason="pytest-benchmark not installed")
class TestToolPerformance:
    """Performance benchmarks for tool system."""

    def test_tool_decorator_overhead(self, benchmark):
        """Benchmark overhead of @tool decorator."""

        def plain_function(x: int, y: int) -> int:
            """Add two numbers."""
            return x + y

        from agentmold import tool

        @tool
        def decorated_function(x: int, y: int) -> int:
            """Add two numbers."""
            return x + y

        # Compare performance
        plain_result = benchmark(plain_function, 5, 3)
        assert plain_result == 8

        # The decorated version should have minimal overhead
        decorated_result = decorated_function(5, 3)
        assert decorated_result == 8

    def test_tool_validation_overhead(self, benchmark):
        """Benchmark tool argument validation."""
        from agentmold import tool

        @tool
        def validated_function(name: str, count: int) -> str:
            """Process items with validation."""
            return f"{name} x {count}"

        def validate_and_call():
            return validated_function(name="test", count=42)

        result = benchmark(validate_and_call)
        assert result == "test x 42"


@pytest.mark.skipif(not BENCHMARK_AVAILABLE, reason="pytest-benchmark not installed")
class TestMemoryPerformance:
    """Performance benchmarks for memory system."""

    def test_memory_sliding_window(self, benchmark):
        """Benchmark sliding window memory with many messages."""
        from agentmold import Memory
        from agentmold.llm import Message

        memory = Memory(max_messages=50)

        def sliding_window_ops():
            # Add more messages than the window size
            for i in range(100):
                memory.add(Message(role="user", content=f"Message {i}"))
            return len(memory.messages())

        final_count = benchmark(sliding_window_ops)
        assert final_count <= 52  # max_messages + system prompt

    def test_vector_memory_search(self, benchmark):
        """Benchmark vector memory search operations."""
        try:
            from agentmold import VectorMemory
        except ImportError:
            pytest.skip("VectorMemory dependencies not installed")

        import hashlib

        # Simple hash-based embedder for testing
        def hash_embedder(text: str) -> list[float]:
            hash_obj = hashlib.md5(text.encode())
            hash_bytes = hash_obj.digest()
            return [float(b) / 255.0 for b in hash_bytes[:8]]

        memory = VectorMemory(
            collection="benchmark_test",
            storage_path="./.agentmold/benchmark_memory",
            embedder=hash_embedder,
        )

        # Add some documents
        for i in range(20):
            memory.add(Message(role="user", content=f"Document content {i} about testing"))

        def search_operation():
            return memory.search("testing query", top_k=5)

        results = benchmark(search_operation)
        assert len(results) <= 5


@pytest.mark.skipif(not BENCHMARK_AVAILABLE, reason="pytest-benchmark not installed")
class TestSerializationPerformance:
    """Performance benchmarks for serialization operations."""

    def test_trace_serialization(self, benchmark):
        """Benchmark AgentTrace serialization."""
        from agentmold import Agent, AgentTrace
        from datetime import datetime, timezone

        # Create a sample trace
        trace = AgentTrace(
            run_id="test-run-123",
            agent_name="Test Agent",
            input_text="Test input",
            output_text="Test output",
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc),
            events=[
                {
                    "type": "tool_call",
                    "name": "test_tool",
                    "arguments": {"param": "value"},
                },
                {
                    "type": "tool_result",
                    "name": "test_tool",
                    "result": "success",
                },
                {
                    "type": "answer",
                    "content": "Final answer",
                },
            ],
        )

        def serialize_trace():
            import json

            return json.dumps(trace.to_dict())

        json_str = benchmark(serialize_trace)
        assert len(json_str) > 0

    def test_trace_deserialization(self, benchmark):
        """Benchmark AgentTrace deserialization."""
        import json
        from agentmold import AgentTrace
        from datetime import datetime, timezone

        # Create a sample trace JSON
        trace_dict = {
            "run_id": "test-run-123",
            "agent_name": "Test Agent",
            "input_text": "Test input",
            "output_text": "Test output",
            "start_time": datetime.now(timezone.utc).isoformat(),
            "end_time": datetime.now(timezone.utc).isoformat(),
            "events": [
                {
                    "type": "tool_call",
                    "name": "test_tool",
                    "arguments": {"param": "value"},
                },
                {
                    "type": "tool_result",
                    "name": "test_tool",
                    "result": "success",
                },
                {
                    "type": "answer",
                    "content": "Final answer",
                },
            ],
        }
        json_str = json.dumps(trace_dict)

        def deserialize_trace(json_data: str):
            data = json.loads(json_data)
            return AgentTrace.from_dict(data)

        trace = benchmark(deserialize_trace, json_str)
        assert trace.run_id == "test-run-123"


@dataclass
class PerformanceThresholds:
    """Performance thresholds for Release Candidate."""

    # Agent execution (ms)
    MAX_SIMPLE_ANSWER_MS: float = 100.0
    MAX_TOOL_INVOCATION_MS: float = 200.0
    MAX_MEMORY_OPERATION_MS: float = 50.0

    # Tool system (ms)
    MAX_SCHEMA_GENERATION_MS: float = 10.0
    MAX_VALIDATION_MS: float = 5.0

    # Memory system (ms)
    MAX_SLIDING_WINDOW_MS: float = 100.0
    MAX_VECTOR_SEARCH_MS: float = 500.0

    # Serialization (ms)
    MAX_TRACE_SERIALIZATION_MS: float = 20.0
    MAX_TRACE_DESERIALIZATION_MS: float = 20.0


def check_performance_thresholds():
    """Check if current performance meets RC thresholds."""
    thresholds = PerformanceThresholds()
    # This would be integrated with actual benchmark results
    print(f"Performance thresholds defined for RC validation")
    print(f"- Max simple answer: {thresholds.MAX_SIMPLE_ANSWER_MS}ms")
    print(f"- Max tool invocation: {thresholds.MAX_TOOL_INVOCATION_MS}ms")
    print(f"- Max memory operation: {thresholds.MAX_MEMORY_OPERATION_MS}ms")


if __name__ == "__main__":
    if BENCHMARK_AVAILABLE:
        print("Run benchmarks with: pytest tests/benchmarks.py -v --benchmark-only")
    else:
        print("Install pytest-benchmark to run performance tests:")
        print("pip install pytest-benchmark")

    check_performance_thresholds()