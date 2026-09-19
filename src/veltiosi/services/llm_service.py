"""LLM service with provider abstraction and fallback support."""

import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union

from ..models import NoteRecord, QueryResult
from ..settings import settings

logger = logging.getLogger(__name__)


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    def generate_content(
        self,
        prompt: str,
        context: Optional[str] = None,
        task_type: str = "default",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Optional[str]:
        """Generate content using the LLM."""
        pass

    @abstractmethod
    def test_connection(self) -> bool:
        """Test connection to the LLM API."""
        pass


class GeminiProvider(LLMProvider):
    """Google Gemini provider."""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize Gemini provider."""
        self.api_key = api_key or settings.google_api_key

        if not self.api_key:
            logger.warning("Google API key not configured")
            self._available = False
            return

        try:
            import google.generativeai as genai
            from google.generativeai.types import HarmCategory, HarmBlockThreshold

            self.genai = genai
            self.HarmCategory = HarmCategory
            self.HarmBlockThreshold = HarmBlockThreshold

            genai.configure(api_key=self.api_key)
            self.model_policy = settings.llm_config.model_policy
            self.timeouts = settings.llm_config.timeouts
            self.generation_config = settings.llm_config.generation
            self.prompts = settings.llm_config.prompts

            self.default_model = self.model_policy.get("default", "gemini-2.0-flash-exp")
            self._available = True

            logger.info(f"Gemini provider initialized with model: {self.default_model}")

        except ImportError:
            logger.error("google-generativeai package not installed")
            self._available = False
        except Exception as e:
            logger.error(f"Failed to initialize Gemini provider: {e}")
            self._available = False

    def _get_model(self, task_type: str = "default") -> str:
        """Get appropriate model for task type."""
        model_map = self.model_policy.get("task_map", {})
        return model_map.get(task_type, self.default_model)

    def _get_safety_settings(self) -> Dict[Any, Any]:
        """Get safety settings."""
        return {
            self.HarmCategory.HARM_CATEGORY_HARASSMENT: self.HarmBlockThreshold.BLOCK_NONE,
            self.HarmCategory.HARM_CATEGORY_HATE_SPEECH: self.HarmBlockThreshold.BLOCK_NONE,
            self.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: self.HarmBlockThreshold.BLOCK_NONE,
            self.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: self.HarmBlockThreshold.BLOCK_NONE,
        }

    def generate_content(
        self,
        prompt: str,
        context: Optional[str] = None,
        task_type: str = "default",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Optional[str]:
        """Generate content using Gemini."""
        if not self._available or not self.api_key:
            logger.error("Gemini provider not available")
            return None

        try:
            model_name = self._get_model(task_type)
            model = self.genai.GenerativeModel(model_name)

            # Build full prompt with context
            full_prompt = prompt
            if context:
                full_prompt = f"Context:\n{context}\n\nTask:\n{prompt}"

            # Configure generation
            config = {
                "temperature": temperature or self.generation_config.get("temperature", 0.7),
                "max_output_tokens": max_tokens or self.generation_config.get("max_tokens", 2048),
                "top_p": self.generation_config.get("top_p", 0.95),
                "top_k": self.generation_config.get("top_k", 40),
            }

            # Generate response
            response = model.generate_content(
                full_prompt, generation_config=config, safety_settings=self._get_safety_settings()
            )

            if response.text:
                return response.text.strip()
            else:
                logger.warning(f"Empty response from Gemini for task: {task_type}")
                return None

        except Exception as e:
            logger.error(f"Failed to generate content with Gemini: {e}")
            return None

    def test_connection(self) -> bool:
        """Test connection to Gemini API."""
        if not self._available or not self.api_key:
            logger.error("Gemini provider not available")
            return False

        try:
            # Simple test generation
            test_prompt = "Say 'Hello' if you're working."
            response = self.generate_content(test_prompt, task_type="default")

            if response and "Hello" in response:
                logger.info("Gemini connection test successful")
                return True
            else:
                logger.warning(f"Unexpected response from Gemini: {response}")
                return False

        except Exception as e:
            logger.error(f"Gemini connection test failed: {e}")
            return False


class OpenRouterProvider(LLMProvider):
    """Google Gemini (and other models) via OpenRouter's chat-completions API.

    Uses the shared ``OPENROUTER_API_KEY`` (already trusted by Jev), so the
    generative synthesis/query path no longer depends on a native Google key.
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None) -> None:
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self.model = model or os.getenv("VELTIOSI_LLM_MODEL", "google/gemini-2.5-flash")
        self._available = bool(self.api_key)
        if not self._available:
            logger.warning("OpenRouter API key not configured")

    def generate_content(
        self,
        prompt: str,
        context: Optional[str] = None,
        task_type: str = "default",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Optional[str]:
        if not self._available:
            return None
        try:
            import requests  # noqa: F401 — guarded; absence degrades to None
        except Exception:
            return None

        full_prompt = prompt
        if context:
            full_prompt = f"Context:\n{context}\n\nTask:\n{prompt}"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a precise assistant for a personal knowledge base."},
                {"role": "user", "content": full_prompt},
            ],
            "temperature": temperature if temperature is not None else 0.7,
            "max_tokens": max_tokens or 2048,
        }
        try:
            resp = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=120,
            )
        except Exception as e:  # noqa: BLE001 — fail-open
            logger.error(f"OpenRouter request failed: {e}")
            return None

        if resp.status_code != 200:
            logger.warning(f"OpenRouter HTTP {resp.status_code}: {(resp.text or '')[:200]}")
            return None

        try:
            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content")
        except Exception as e:  # noqa: BLE001
            logger.error(f"OpenRouter response parse failed: {e}")
            return None

        return content.strip() if content else None

    def test_connection(self) -> bool:
        return self._available


class MockProvider(LLMProvider):
    """Mock provider for testing and fallback."""

    def __init__(self):
        """Initialize mock provider."""
        self._available = True
        logger.info("Mock provider initialized")

    def generate_content(
        self,
        prompt: str,
        context: Optional[str] = None,
        task_type: str = "default",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Optional[str]:
        """Generate mock content."""
        if not self._available:
            return None

        # Simple mock responses based on task type
        mock_responses = {
            "ingest": "Mock ingest response: Key takeaways extracted, categories identified.",
            "query": "Mock query response: Based on the provided context, here's the answer.",
            "synthesis": "Mock synthesis: Weekly insights generated.",
            "classification": '{"primary_root_category": "mental", "secondary_root_categories": [], "subcategories": ["learning"], "note_type": "concept"}',
            "default": "Mock response for testing.",
        }

        response = mock_responses.get(task_type, mock_responses["default"])

        # Add context if provided
        if context:
            response = f"Context: {context[:100]}...\n\n{response}"

        return response

    def test_connection(self) -> bool:
        """Mock connection test always succeeds."""
        return True


class LLMService:
    """Main LLM service with fallback support."""

    def __init__(self):
        """Initialize LLM service with configured providers."""
        self.providers: List[LLMProvider] = []
        self._initialize_providers()

    def _initialize_providers(self):
        """Initialize providers based on configuration."""
        provider_config = settings.llm_config.provider

        # OpenRouter (calls Gemini and others) — primary when a key is present.
        openrouter = OpenRouterProvider()
        if openrouter.test_connection():
            self.providers.append(openrouter)
            logger.info(f"OpenRouter provider added ({openrouter.model})")

        # Native Google Gemini — secondary (legacy path).
        if provider_config == "google" and settings.google_api_key:
            gemini = GeminiProvider()
            if gemini.test_connection():
                self.providers.append(gemini)
                logger.info("Gemini provider added")

        # Always add mock provider as last resort fallback
        self.providers.append(MockProvider())
        logger.info(f"LLM service initialized with {len(self.providers)} providers")

    def generate_content(
        self,
        prompt: str,
        context: Optional[str] = None,
        task_type: str = "default",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        max_retries: int = 3,
    ) -> Optional[str]:
        """Generate content with fallback through providers."""
        for attempt in range(max_retries):
            for provider in self.providers:
                try:
                    logger.debug(f"Attempt {attempt + 1} with {provider.__class__.__name__}")
                    result = provider.generate_content(
                        prompt=prompt,
                        context=context,
                        task_type=task_type,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )

                    if result:
                        logger.info(f"Generated content using {provider.__class__.__name__}")
                        return result

                except Exception as e:
                    logger.warning(f"Provider {provider.__class__.__name__} failed: {e}")
                    continue

        logger.error(f"All providers failed after {max_retries} attempts")
        return None

    def generate_ingest_summary(
        self,
        source_title: str,
        source_type: str,
        source_content: str,
        wiki_context: str,
    ) -> Optional[str]:
        """Generate ingest summary using configured prompts."""
        prompt_template = settings.llm_config.prompts.get("ingest", {}).get("user_template")
        if not prompt_template:
            logger.error("No ingest prompt template found")
            return None

        prompt = prompt_template.format(
            source_title=source_title,
            source_type=source_type,
            source_content=source_content,
            wiki_context=wiki_context,
        )

        system_prompt = settings.llm_config.prompts.get("ingest", {}).get("system", "")
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt

        return self.generate_content(full_prompt, task_type="ingest")

    def generate_query_answer(
        self,
        question: str,
        wiki_context: str,
    ) -> Optional[QueryResult]:
        """Generate query answer with citations."""
        prompt_template = settings.llm_config.prompts.get("query", {}).get("user_template")
        if not prompt_template:
            logger.error("No query prompt template found")
            return None

        prompt = prompt_template.format(
            question=question,
            wiki_context=wiki_context,
        )

        system_prompt = settings.llm_config.prompts.get("query", {}).get("system", "")
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt

        response = self.generate_content(full_prompt, task_type="query")
        if not response:
            return None

        # Parse response for citations (simple [[Page Name]] extraction)
        import re

        citations = re.findall(r"\[\[([^\]]+)\]\]", response)

        # Simple coverage gap detection
        coverage_gaps = []
        lines = response.split("\n")
        for line in lines:
            if any(word in line.lower() for word in ["gap", "missing", "unclear", "unknown"]):
                coverage_gaps.append(line.strip())

        return QueryResult(
            answer=response,
            citations=list(set(citations)),  # Deduplicate
            confidence=0.8,
            coverage_gaps=coverage_gaps[:5],  # Limit to top 5
            suggested_new_notes=[],
        )

    def generate_weekly_synthesis(
        self,
        completed_tasks: List[str],
        updated_pages: List[str],
        new_sources: List[str],
        category_points: Dict[str, int],
    ) -> Optional[str]:
        """Generate weekly synthesis note."""
        prompt_template = settings.llm_config.prompts.get("synthesis", {}).get("user_template")
        if not prompt_template:
            logger.error("No synthesis prompt template found")
            return None

        # Format category points
        category_text = "\n".join(
            [f"- {cat}: {points} points" for cat, points in category_points.items()]
        )

        prompt = prompt_template.format(
            completed_tasks="\n".join([f"- {task}" for task in completed_tasks]),
            updated_pages="\n".join([f"- {page}" for page in updated_pages]),
            new_sources="\n".join([f"- {source}" for source in new_sources]),
            category_points=category_text,
        )

        system_prompt = settings.llm_config.prompts.get("synthesis", {}).get("system", "")
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt

        return self.generate_content(full_prompt, task_type="synthesis")

    def classify_note(
        self,
        title: str,
        content: str,
        domain_folder: str,
    ) -> Optional[Dict[str, Any]]:
        """Classify note using LLM."""
        prompt_template = settings.llm_config.prompts.get("classification", {}).get("user_template")
        if not prompt_template:
            logger.error("No classification prompt template found")
            return None

        prompt = prompt_template.format(
            title=title,
            content=content[:2000],  # Limit content length
            domain_folder=domain_folder,
        )

        system_prompt = settings.llm_config.prompts.get("classification", {}).get("system", "")
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt

        response = self.generate_content(full_prompt, task_type="classification")
        if not response:
            return None

        try:
            # Try to parse JSON response
            # Remove any markdown code blocks
            clean_response = response.strip()
            if clean_response.startswith("```"):
                lines = clean_response.split("\n")
                clean_response = "\n".join(lines[1:-1]) if len(lines) > 2 else clean_response
                clean_response = clean_response.strip("`")

            return json.loads(clean_response)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse JSON from classification response: {response}")
            return None

    def test_all_connections(self) -> Dict[str, bool]:
        """Test connections for all providers."""
        results = {}
        for provider in self.providers:
            provider_name = provider.__class__.__name__
            results[provider_name] = provider.test_connection()
        return results


# Global LLM service instance
llm_service = LLMService()
