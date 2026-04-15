"""LLM integration for MemText.

Supports local models via Ollama (free) or OpenAI as optional.
Requires: pip install memtext[llm]
"""

import os
import json
import re
from typing import Optional, List, Dict, Any
from dataclasses import dataclass


@dataclass
class SynthesisResult:
    """Result from LLM synthesis."""

    summary: str
    memories: List[Dict[str, Any]]
    tags: List[str]
    relationships: List[str]


def get_llm_client():
    """Get available LLM client."""
    try:
        from openai import OpenAI

        return OpenAI
    except ImportError:
        return None


def is_local_available() -> bool:
    """Check if Ollama is running locally."""
    try:
        import urllib.request

        req = urllib.request.Request("http://localhost:11434/api/tags")
        urllib.request.urlopen(req, timeout=2)
        return True
    except Exception:
        return False


def synthesize_with_local(
    context: str, model: str = "llama3"
) -> Optional[SynthesisResult]:
    """Synthesize using local Ollama model."""
    try:
        import urllib.request
        import urllib.parse

        prompt = f"""Extract key memories from this context. Return a JSON object with:
- "summary": Brief summary (50 words max)
- "memories": Array of {{"title", "content", "type", "tags"}}
- "tags": Array of relevant tags

Context:
{context[:4000]}
"""

        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
        )

        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))
            response_data = json.loads(result.get("response", "{}"))

            return SynthesisResult(
                summary=response_data.get("summary", ""),
                memories=response_data.get("memories", []),
                tags=response_data.get("tags", []),
                relationships=response_data.get("relationships", []),
            )
    except Exception as e:
        return None


def synthesize_with_openai(
    context: str, model: str = "gpt-4o-mini"
) -> Optional[SynthesisResult]:
    """Synthesize using OpenAI (requires paid API key)."""
    client = get_llm_client()
    if not client:
        return None

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None

    try:
        client = client(api_key=api_key)

        prompt = f"""Extract key memories from this context. Return ONLY valid JSON with this exact structure:
{{
    "summary": "Brief summary (50 words max)",
    "memories": [{{"title": "string", "content": "string", "type": "decision|pattern|convention", "tags": ["tag1"]}}],
    "tags": ["relevant", "tags"],
    "relationships": ["related entry pairs"]
}}

Context:
{context[:4000]}
"""

        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )

        result_text = response.choices[0].message.content
        response_data = json.loads(result_text)

        return SynthesisResult(
            summary=response_data.get("summary", ""),
            memories=response_data.get("memories", []),
            tags=response_data.get("tags", []),
            relationships=response_data.get("relationships", []),
        )
    except Exception as e:
        return None


def synthesize(context: str) -> Optional[SynthesisResult]:
    """Synthesize using available LLM. Tries: local Ollama → OpenAI → rule-based fallback."""
    result = synthesize_with_local(context)
    if result:
        return result

    result = synthesize_with_openai(context)
    if result:
        return result

    return None


def synthesize_rule_based(context: str) -> SynthesisResult:
    """Rule-based synthesis when no LLM available."""
    from memtext.memory_logic import DecisionExtractor

    extractor = DecisionExtractor()
    extracted = extractor.extract_all(context)

    memories = []
    for item in extracted:
        memories.append(
            {
                "title": f"{item.get('category', 'memory')}: {item.get('content', '')[:50]}",
                "content": item.get("content", ""),
                "type": item.get("type", "note"),
                "tags": [item.get("category", "memory")],
            }
        )

    tags = list(set(item.get("category", "") for item in extracted))

    return SynthesisResult(
        summary=f"Extracted {len(memories)} items from context",
        memories=memories,
        tags=tags,
        relationships=[],
    )


def get_synthesis_prompt() -> str:
    """Get prompt used for LLM synthesis."""
    return """Extract key memories from this context. Return ONLY valid JSON with:
- "summary": Brief summary (50 words max)
- "memories": Array of {title, content, type, tags}
- "tags": Array of relevant tags
- "relationships": Array of related entry pairs"""


def check_llm_available() -> Dict[str, bool]:
    """Check which LLM options are available."""
    return {
        "openai": get_llm_client() is not None
        and bool(os.environ.get("OPENAI_API_KEY")),
        "local": is_local_available(),
    }


class AutoTagger:
    """Auto-tag content using patterns or LLM."""

    TAG_PATTERNS = {
        "database": [
            "sql",
            "postgresql",
            "mysql",
            "sqlite",
            "mongodb",
            "redis",
            "database",
            "db",
        ],
        "api": ["api", "rest", "endpoint", "http", "graphql", "crud"],
        "auth": ["auth", "login", "jwt", "oauth", "password", "token", "session"],
        "frontend": [
            "react",
            "vue",
            "angular",
            "css",
            "html",
            "javascript",
            "ui",
            "ux",
        ],
        "backend": ["server", "backend", "node", "python", "java", "golang"],
        "devops": ["docker", "kubernetes", "k8s", "ci", "cd", "deploy", "aws", "cloud"],
        "testing": ["test", "pytest", "jest", "unittest", "coverage", "mock"],
        "security": ["security", "encrypt", "ssl", "tls", "https", "vulnerability"],
        "performance": [
            "performance",
            "optimize",
            "cache",
            "latency",
            "speed",
            "memory",
        ],
        "architecture": [
            "pattern",
            "architecture",
            "design",
            "microservice",
            "monolith",
        ],
    }

    def tag_content(self, content: str) -> List[str]:
        """Tag content based on patterns."""
        content_lower = content.lower()
        tags = []

        for tag, keywords in self.TAG_PATTERNS.items():
            if any(kw in content_lower for kw in keywords):
                tags.append(tag)

        return tags[:5]

    def tag_with_llm(self, content: str) -> Optional[List[str]]:
        """Tag content using LLM (if available)."""
        result = synthesize(content)
        if result:
            return result.tags
        return None


def auto_tag(content: str) -> List[str]:
    """Auto-tag content using available methods."""
    tagger = AutoTagger()
    tags = tagger.tag_content(content)

    if not tags:
        llm_tags = tagger.tag_with_llm(content)
        if llm_tags:
            tags = llm_tags

    return tags
