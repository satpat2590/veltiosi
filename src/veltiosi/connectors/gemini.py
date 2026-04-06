"""Google Gemini LLM connector."""

import json
import logging
import time
from typing import Any, Dict, List, Optional

import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

from ..models import NoteRecord, QueryResult
from ..settings import settings

logger = logging.getLogger(__name__)


class GeminiConnector:
    """Connector for Google Gemini LLM."""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize Gemini connector."""
        self.api_key = api_key or settings.google_api_key

        if not self.api_key:
            logger.warning("Google API key not configured")
            return

        try:
            genai.configure(api_key=self.api_key)
            self.model_policy = settings.llm_config.model_policy
            self.timeouts = settings.llm_config.timeouts
            self.generation_config = settings.llm_config.generation
            self.prompts = settings.llm_config.prompts

            # Get default model from policy
            self.default_model = self.model_policy.get("default", "gemini-2.0-flash-exp")

            logger.info(f"Gemini connector initialized with model: {self.default_model}")

        except Exception as e:
            logger.error(f"Failed to initialize Gemini connector: {e}")

    def _get_model(self, task_type: str = "default") -> str:
        """Get appropriate model for task type."""
        model_map = self.model_policy.get("task_map", {})
        return model_map.get(task_type, self.default_model)

    def _get_safety_settings(self) -> Dict[HarmCategory, HarmBlockThreshold]:
        """Get safety settings."""
        return {
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
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
        if not self.api_key:
            logger.error("Google API key not configured")
            return None

        try:
            model_name = self._get_model(task_type)
            model = genai.GenerativeModel(model_name)

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

    def generate_note_content(
        self,
        note_type: str,
        title: str,
        context_notes: List[NoteRecord],
        additional_context: Optional[str] = None,
    ) -> Optional[str]:
        """Generate content for a specific note type."""
        prompt_template = self.prompts.get(note_type, {}).get("template")

        if not prompt_template:
            logger.error(f"No prompt template found for note type: {note_type}")
            return None

        # Build context from related notes
        context_text = ""
        if context_notes:
            context_text = "Related notes:\n"
            for note in context_notes:
                try:
                    with open(note.path, "r") as f:
                        content = f.read()
                        context_text += f"\n--- {note.title} ---\n{content[:1000]}\n"
                except Exception as e:
                    logger.warning(f"Failed to read note {note.path}: {e}")

        if additional_context:
            context_text += f"\nAdditional context:\n{additional_context}"

        # Fill template
        prompt = prompt_template.format(title=title, context=context_text)

        return self.generate_content(prompt, task_type=note_type)

    def generate_index_content(
        self, category: str, notes: List[NoteRecord], index_type: str = "moc"
    ) -> Optional[str]:
        """Generate index content for a category."""
        prompt_template = self.prompts.get("index_generation", {}).get(index_type)

        if not prompt_template:
            logger.error(f"No prompt template found for index type: {index_type}")
            return None

        # Organize notes by subcategory
        notes_by_subcat = {}
        for note in notes:
            for subcat in note.subcategories:
                if subcat not in notes_by_subcat:
                    notes_by_subcat[subcat] = []
                notes_by_subcat[subcat].append(note)

        # Build context
        context_text = f"Category: {category}\n\n"
        for subcat, subcat_notes in notes_by_subcat.items():
            context_text += f"## {subcat}\n"
            for note in subcat_notes:
                context_text += f"- [[{note.title}]]"
                if note.note_type.value:
                    context_text += f" ({note.note_type.value})"
                context_text += "\n"
            context_text += "\n"

        prompt = prompt_template.format(category=category, notes_context=context_text)

        return self.generate_content(prompt, task_type="index_generation")

    def query_wiki(
        self, question: str, relevant_notes: List[NoteRecord], max_notes: int = 10
    ) -> Optional[QueryResult]:
        """Query the wiki using Gemini."""
        prompt_template = self.prompts.get("query", {}).get("template")

        if not prompt_template:
            logger.error("No query prompt template found")
            return None

        # Build context from relevant notes
        context_text = ""
        citations = []

        for i, note in enumerate(relevant_notes[:max_notes]):
            try:
                with open(note.path, "r") as f:
                    content = f.read()
                    context_text += f"\n--- Document {i + 1}: [[{note.title}]] ---\n"
                    context_text += content[:1500] + "\n"
                    citations.append(f"[[{note.title}]]")
            except Exception as e:
                logger.warning(f"Failed to read note {note.path}: {e}")

        prompt = prompt_template.format(question=question, context=context_text)

        response = self.generate_content(prompt, task_type="query")

        if not response:
            return None

        # Parse response for coverage gaps and suggestions
        coverage_gaps = []
        suggested_notes = []

        # Simple parsing - could be enhanced
        lines = response.split("\n")
        for line in lines:
            if "gap:" in line.lower() or "missing:" in line.lower():
                gap = line.split(":", 1)[1].strip() if ":" in line else line.strip()
                coverage_gaps.append(gap)
            elif "suggest:" in line.lower() or "create:" in line.lower():
                suggestion = line.split(":", 1)[1].strip() if ":" in line else line.strip()
                suggested_notes.append(suggestion)

        return QueryResult(
            answer=response,
            citations=citations,
            confidence=0.8,  # Could be calculated based on response quality
            coverage_gaps=coverage_gaps,
            suggested_new_notes=suggested_notes,
        )

    def analyze_task_for_wiki_update(
        self, task_title: str, task_description: Optional[str], existing_notes: List[NoteRecord]
    ) -> Dict[str, Any]:
        """Analyze a task to determine wiki update strategy."""
        prompt_template = self.prompts.get("task_analysis", {}).get("template")

        if not prompt_template:
            logger.error("No task analysis prompt template found")
            return {}

        # Build context from existing notes
        context_text = "Existing related notes:\n"
        for note in existing_notes[:5]:
            context_text += f"- [[{note.title}]]: {note.note_type.value}\n"

        task_text = f"Task: {task_title}"
        if task_description:
            task_text += f"\nDescription: {task_description}"

        prompt = prompt_template.format(task=task_text, existing_notes=context_text)

        response = self.generate_content(prompt, task_type="task_analysis")

        if not response:
            return {}

        # Parse JSON response if possible
        try:
            # Try to extract JSON from response
            lines = response.split("\n")
            json_start = None
            json_end = None

            for i, line in enumerate(lines):
                if line.strip().startswith("{"):
                    json_start = i
                    break

            if json_start is not None:
                for i in range(json_start, len(lines)):
                    if lines[i].strip().endswith("}"):
                        json_end = i
                        break

                if json_end is not None:
                    json_str = "\n".join(lines[json_start : json_end + 1])
                    return json.loads(json_str)

        except json.JSONDecodeError:
            logger.warning("Failed to parse JSON from Gemini response")

        # Fallback: return structured text
        return {"analysis": response, "recommended_action": "create_or_update", "confidence": 0.7}

    def test_connection(self) -> bool:
        """Test connection to Gemini API."""
        if not self.api_key:
            logger.error("Google API key not configured")
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
