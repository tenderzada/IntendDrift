"""Unified LLM Client for IntentDrift Pipeline.

Supports Anthropic (Claude) and OpenAI (GPT) APIs with a common interface.
"""

import json
import logging
import os
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    content: str
    model: str
    usage: dict


class UnifiedLLMClient:
    """Unified client that routes to Anthropic or OpenAI based on model name."""

    def __init__(self):
        self._anthropic_client = None
        self._openai_client = None

    def _get_anthropic(self):
        if self._anthropic_client is None:
            import anthropic
            self._anthropic_client = anthropic.Anthropic(
                api_key=os.environ.get("ANTHROPIC_API_KEY")
            )
        return self._anthropic_client

    def _get_openai(self):
        if self._openai_client is None:
            import openai
            self._openai_client = openai.OpenAI(
                api_key=os.environ.get("OPENAI_API_KEY")
            )
        return self._openai_client

    def _is_anthropic_model(self, model: str) -> bool:
        return any(k in model.lower() for k in ["claude", "sonnet", "haiku", "opus"])

    def _is_openai_model(self, model: str) -> bool:
        return any(k in model.lower() for k in ["gpt", "o1", "o3"])

    def chat(
        self,
        model: str,
        messages: list[dict],
        system: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Send a chat request to the appropriate API."""
        if self._is_anthropic_model(model):
            return self._call_anthropic(model, messages, system, temperature, max_tokens)
        elif self._is_openai_model(model):
            return self._call_openai(model, messages, system, temperature, max_tokens)
        else:
            # Default to OpenAI-compatible API (e.g., for DeepSeek, Gemini via proxy)
            return self._call_openai(model, messages, system, temperature, max_tokens)

    def _call_anthropic(
        self, model, messages, system, temperature, max_tokens
    ) -> LLMResponse:
        client = self._get_anthropic()
        kwargs = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system:
            kwargs["system"] = system

        response = client.messages.create(**kwargs)
        return LLMResponse(
            content=response.content[0].text,
            model=response.model,
            usage={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
        )

    def _call_openai(
        self, model, messages, system, temperature, max_tokens
    ) -> LLMResponse:
        client = self._get_openai()
        full_messages = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        response = client.chat.completions.create(
            model=model,
            messages=full_messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        choice = response.choices[0]
        return LLMResponse(
            content=choice.message.content,
            model=response.model,
            usage={
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens,
            },
        )


def parse_json_response(text: str) -> dict | list | None:
    """Extract and parse JSON from LLM response, handling markdown code blocks."""
    text = text.strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code block
    if "```" in text:
        blocks = text.split("```")
        for i, block in enumerate(blocks):
            if i % 2 == 1:  # odd indices are inside code blocks
                # Remove optional language tag
                content = block.strip()
                if content.startswith("json"):
                    content = content[4:].strip()
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    continue

    # Try finding JSON object/array boundaries
    for start_char, end_char in [("{", "}"), ("[", "]")]:
        start = text.find(start_char)
        end = text.rfind(end_char)
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                continue

    logger.warning(f"Could not parse JSON from response: {text[:200]}...")
    return None
