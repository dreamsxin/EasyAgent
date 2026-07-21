"""Build a transparent retrieval-augmented agent with an in-memory corpus."""

import re

from agentmold import Agent, LogLevel, tool

CORPUS = [
    {"id": "R1", "text": "Retrieval selects context before an answer is generated."},
    {"id": "R2", "text": "Small corpora make relevance decisions easy to inspect."},
    {"id": "R3", "text": "Answers should cite retrieved chunk identifiers."},
]


def words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


@tool
def retrieve(query: str) -> str:
    """Retrieve corpus chunks sharing terms with a query.

    Args:
        query: Question or search terms.
    """
    terms = words(query)
    ranked = [(len(terms & words(chunk["text"])), chunk) for chunk in CORPUS]
    matches = [
        chunk
        for score, chunk in sorted(ranked, key=lambda item: item[0], reverse=True)
        if score > 0
    ]
    return "\n".join(f"[{chunk['id']}] {chunk['text']}" for chunk in matches)


def build_agent() -> Agent:
    return Agent(
        name="Offline RAG",
        instructions=(
            "Retrieve context before answering. Cite chunk IDs and say when the corpus "
            "does not contain enough evidence."
        ),
        tools=[retrieve],
        llm="mock",
        log_level=LogLevel.SILENT,
    )


def main() -> None:
    agent = build_agent()
    print(agent("tool: retrieval context"))


if __name__ == "__main__":
    main()
