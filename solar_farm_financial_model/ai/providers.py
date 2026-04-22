from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Dict, List
from urllib.request import Request, urlopen

from openai import OpenAI


@dataclass
class ProviderCapabilities:
    reasoning: bool
    long_context: bool
    tool_use: bool
    web_search: bool
    vision: bool
    streaming: bool


@dataclass
class LLMProviderConfig:
    provider_name: str = "openai"
    model_name: str = "gpt-5-mini"
    api_key: str = ""
    base_url: str = ""
    temperature: float = 0.2
    max_tokens: int = 1200
    reasoning_mode: str = "medium"
    enable_tools: bool = True
    enable_web_search: bool = True


PROVIDER_SPECS: Dict[str, Dict[str, object]] = {
    "openai": {
        "label": "OpenAI",
        "models": ["gpt-5.2", "gpt-5-mini", "gpt-5-nano"],
        "default_base_url": "",
        "capabilities": ProviderCapabilities(True, True, True, True, True, True),
    },
    "anthropic": {
        "label": "Anthropic Claude",
        "models": ["claude-opus-4-1", "claude-sonnet-4-0"],
        "default_base_url": "https://api.anthropic.com",
        "capabilities": ProviderCapabilities(True, True, True, False, True, True),
    },
    "google": {
        "label": "Google Gemini",
        "models": ["gemini-2.5-pro"],
        "default_base_url": "https://generativelanguage.googleapis.com",
        "capabilities": ProviderCapabilities(True, True, True, True, True, True),
    },
    "mistral": {
        "label": "Mistral",
        "models": ["mistral-large-latest", "mistral-medium-latest", "magistral-medium-latest"],
        "default_base_url": "https://api.mistral.ai",
        "capabilities": ProviderCapabilities(True, True, True, False, False, True),
    },
    "cohere": {
        "label": "Cohere",
        "models": ["command-a-03-2025", "command-r-plus"],
        "default_base_url": "https://api.cohere.com",
        "capabilities": ProviderCapabilities(False, True, True, False, False, True),
    },
    "xai": {
        "label": "xAI Grok",
        "models": ["grok-4", "grok-3-mini"],
        "default_base_url": "https://api.x.ai/v1",
        "capabilities": ProviderCapabilities(True, True, True, False, True, True),
    },
    "deepseek": {
        "label": "DeepSeek",
        "models": ["deepseek-chat", "deepseek-reasoner"],
        "default_base_url": "https://api.deepseek.com/v1",
        "capabilities": ProviderCapabilities(True, True, True, False, False, True),
    },
    "llama": {
        "label": "Meta Llama",
        "models": ["llama-4-maverick-instruct", "llama-4-scout-instruct"],
        "default_base_url": "",
        "capabilities": ProviderCapabilities(False, True, True, False, True, True),
    },
}


def _post_json(url: str, payload: dict, headers: Dict[str, str], timeout: int = 45) -> dict:
    req = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    with urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="ignore")
    if not raw:
        return {}
    return json.loads(raw)


def _messages_to_plain_text(messages: List[dict]) -> str:
    lines: List[str] = []
    for message in messages:
        role = str(message.get("role", "user")).upper()
        content = str(message.get("content", ""))
        lines.append(f"{role}: {content}")
    return "\n\n".join(lines)


class ProviderAdapter:
    def __init__(self, config: LLMProviderConfig):
        self.config = config

    def generate_response(self, messages: List[dict], use_web_search: bool) -> str:
        raise NotImplementedError


class OpenAIResponsesAdapter(ProviderAdapter):
    def generate_response(self, messages: List[dict], use_web_search: bool) -> str:
        client = OpenAI(api_key=self.config.api_key, base_url=self.config.base_url or None)
        tools = [{"type": "web_search"}] if use_web_search else []
        response = client.responses.create(
            model=self.config.model_name,
            reasoning={"effort": self.config.reasoning_mode},
            tools=tools,
            input=messages,
            temperature=self.config.temperature,
            max_output_tokens=self.config.max_tokens,
        )
        return response.output_text


class OpenAICompatibleAdapter(ProviderAdapter):
    """Adapter for providers with OpenAI-compatible endpoints (xAI/DeepSeek/self-hosted)."""

    def generate_response(self, messages: List[dict], use_web_search: bool) -> str:
        if not self.config.base_url:
            raise ValueError(
                f"Provider '{self.config.provider_name}' requires base_url or compatible gateway endpoint."
            )
        client = OpenAI(api_key=self.config.api_key, base_url=self.config.base_url)
        completion = client.chat.completions.create(
            model=self.config.model_name,
            messages=messages,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )
        return completion.choices[0].message.content or ""


class AnthropicAdapter(ProviderAdapter):
    def generate_response(self, messages: List[dict], use_web_search: bool) -> str:
        base = self.config.base_url or provider_default_base_url("anthropic")
        payload = {
            "model": self.config.model_name,
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "messages": [{"role": "user", "content": _messages_to_plain_text(messages)}],
        }
        response = _post_json(
            url=f"{base.rstrip('/')}/v1/messages",
            payload=payload,
            headers={
                "x-api-key": self.config.api_key,
                "anthropic-version": "2023-06-01",
            },
        )
        content = response.get("content", [])
        if not content:
            return ""
        first = content[0] if isinstance(content, list) else {}
        return str(first.get("text", ""))


class GeminiAdapter(ProviderAdapter):
    def generate_response(self, messages: List[dict], use_web_search: bool) -> str:
        base = self.config.base_url or provider_default_base_url("google")
        payload = {
            "generationConfig": {
                "temperature": self.config.temperature,
                "maxOutputTokens": self.config.max_tokens,
            },
            "contents": [{"role": "user", "parts": [{"text": _messages_to_plain_text(messages)}]}],
        }
        response = _post_json(
            url=(
                f"{base.rstrip('/')}/v1beta/models/{self.config.model_name}:generateContent"
                f"?key={self.config.api_key}"
            ),
            payload=payload,
            headers={},
        )
        candidates = response.get("candidates", [])
        if not candidates:
            return ""
        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            return ""
        return str(parts[0].get("text", ""))


class CohereAdapter(ProviderAdapter):
    def generate_response(self, messages: List[dict], use_web_search: bool) -> str:
        base = self.config.base_url or provider_default_base_url("cohere")
        payload = {
            "model": self.config.model_name,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "messages": [{"role": "user", "content": _messages_to_plain_text(messages)}],
        }
        response = _post_json(
            url=f"{base.rstrip('/')}/v2/chat",
            payload=payload,
            headers={"Authorization": f"Bearer {self.config.api_key}"},
        )
        message = response.get("message", {})
        content = message.get("content", [])
        if not content:
            return ""
        first = content[0] if isinstance(content, list) else {}
        return str(first.get("text", ""))


class MistralAdapter(ProviderAdapter):
    def generate_response(self, messages: List[dict], use_web_search: bool) -> str:
        base = self.config.base_url or provider_default_base_url("mistral")
        payload = {
            "model": self.config.model_name,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }
        response = _post_json(
            url=f"{base.rstrip('/')}/v1/chat/completions",
            payload=payload,
            headers={"Authorization": f"Bearer {self.config.api_key}"},
        )
        choices = response.get("choices", [])
        if not choices:
            return ""
        return str(choices[0].get("message", {}).get("content", ""))


def provider_capabilities(provider_name: str) -> ProviderCapabilities:
    return PROVIDER_SPECS.get(provider_name, PROVIDER_SPECS["openai"])["capabilities"]


def provider_models(provider_name: str) -> List[str]:
    return list(PROVIDER_SPECS.get(provider_name, PROVIDER_SPECS["openai"])["models"])


def provider_label(provider_name: str) -> str:
    return str(PROVIDER_SPECS.get(provider_name, PROVIDER_SPECS["openai"])["label"])


def provider_default_base_url(provider_name: str) -> str:
    return str(PROVIDER_SPECS.get(provider_name, PROVIDER_SPECS["openai"])["default_base_url"])


def env_api_key(provider_name: str) -> str:
    env_map = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "google": "GOOGLE_API_KEY",
        "mistral": "MISTRAL_API_KEY",
        "cohere": "COHERE_API_KEY",
        "xai": "XAI_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
        "llama": "LLAMA_API_KEY",
    }
    return os.environ.get(env_map.get(provider_name, ""), "")


def build_adapter(config: LLMProviderConfig) -> ProviderAdapter:
    if config.provider_name == "openai":
        return OpenAIResponsesAdapter(config)
    if config.provider_name == "anthropic":
        return AnthropicAdapter(config)
    if config.provider_name == "google":
        return GeminiAdapter(config)
    if config.provider_name == "cohere":
        return CohereAdapter(config)
    if config.provider_name == "mistral":
        return MistralAdapter(config)
    return OpenAICompatibleAdapter(config)
