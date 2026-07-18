"""Wiki query workflow."""

import logging
import time
from pathlib import Path
from typing import Dict, List, Optional

from ..audit import AuditLogger
from ..models import QueryResult
from ..services.llm_service import llm_service
from ..services.retrieval import RetrievalService
from ..services.wiki_repository import WikiRepository

logger = logging.getLogger(__name__)


class WikiQueryWorkflow:
    """Workflow for querying the wiki."""

    def __init__(self, vault_path: Optional[Path] = None):
        """Initialize wiki query workflow."""
        self.wiki_repo = WikiRepository(vault_path)
        self.retrieval = RetrievalService(self.wiki_repo)

    def query(
        self,
        question: str,
        max_notes: int = 10,
        include_generated: bool = True,
    ) -> Optional[QueryResult]:
        """Query the wiki with a natural language question."""
        logger.info(f"Querying wiki: {question}")

        # Retrieve relevant notes
        relevant_notes = self.retrieval.retrieve_for_query(
            query=question,
            max_notes=max_notes,
        )

        if not relevant_notes:
            logger.warning("No relevant notes found for query")
            return QueryResult(
                answer="No relevant information found in the wiki.",
                citations=[],
                confidence=0.0,
                coverage_gaps=[f"No notes found related to: {question}"],
                suggested_new_notes=[],
            )

        logger.info(f"Found {len(relevant_notes)} relevant notes")

        # Build wiki context from relevant notes
        wiki_context = self._build_wiki_context(relevant_notes)

        # Generate answer using LLM
        result = llm_service.generate_query_answer(
            question=question,
            wiki_context=wiki_context,
        )

        if result:
            logger.info(f"Generated answer with {len(result.citations)} citations")
            return result
        else:
            logger.error("Failed to generate answer")
            return None

    def _build_wiki_context(self, notes: list) -> str:
        """Build context string from relevant notes."""
        context_parts = []

        for i, note in enumerate(notes):
            try:
                content = self.wiki_repo.read_note_content(note.path)
                if content:
                    # Truncate content for context
                    truncated = content[:1500] + "..." if len(content) > 1500 else content
                    context_parts.append(
                        f"--- Document {i + 1}: [[{note.title}]] ---\n{truncated}\n"
                    )
            except Exception as e:
                logger.warning(f"Failed to read note {note.path}: {e}")

        return "\n".join(context_parts)

    def interactive_query(self):
        """Run interactive query session."""
        print("Wiki Query Interactive Mode")
        print("Type 'exit' or 'quit' to end session")
        print("-" * 50)

        while True:
            try:
                question = input("\nQuery: ").strip()

                if question.lower() in ["exit", "quit", "q"]:
                    print("Exiting query session.")
                    break

                if not question:
                    continue

                result = self.query(question)

                if result:
                    print("\n" + "=" * 50)
                    print("ANSWER:")
                    print("=" * 50)
                    print(result.answer)
                    print("\n" + "-" * 50)

                    if result.citations:
                        print("CITATIONS:")
                        for citation in result.citations:
                            print(f"  - [[{citation}]]")

                    if result.coverage_gaps:
                        print("\nCOVERAGE GAPS:")
                        for gap in result.coverage_gaps[:3]:  # Show top 3
                            print(f"  - {gap}")

                    print(f"\nConfidence: {result.confidence:.2f}")
                else:
                    print("Failed to generate answer.")

            except KeyboardInterrupt:
                print("\nExiting query session.")
                break
            except Exception as e:
                logger.error(f"Error during query: {e}")
                print(f"Error: {e}")


def run_query(
    question: str,
    category: Optional[str] = None,
    save_note: bool = False,
    dry_run: bool = False,
) -> Dict[str, any]:
    """Run wiki query workflow."""
    # Start audit log
    audit = AuditLogger()
    run_id = audit.start_run(command="wiki_query", mode="dry-run" if dry_run else "live")

    start_time = time.time()

    try:
        logger.info(f"Starting wiki query workflow: {question}")

        # Initialize workflow
        workflow = WikiQueryWorkflow()

        # Run query
        result = workflow.query(question=question)

        if not result:
            error_msg = "Failed to generate query result"
            logger.error(error_msg)
            audit.log_error(run_id, error_msg)
            audit.complete_run(run_id, status="failure", duration_seconds=time.time() - start_time)
            return {"error": error_msg}

        # Prepare response
        response = {
            "answer": result.answer,
            "citations": result.citations,
            "confidence": result.confidence,
            "coverage_gaps": result.coverage_gaps,
            "suggested_new_notes": result.suggested_new_notes,
        }

        # Save as note if requested
        if save_note and not dry_run:
            note_path = _save_query_as_note(question, result)
            if note_path:
                response["saved_note_path"] = str(note_path)

        # Update audit log
        audit.update_run(
            run_id,
            status="running",
            notes_read=len(result.citations) if result.citations else 0,
        )

        # Complete audit log
        duration = time.time() - start_time
        audit.complete_run(run_id, status="success", duration_seconds=duration)

        logger.info(f"Query completed in {duration:.2f} seconds")
        return response

    except Exception as e:
        logger.error(f"Query workflow failed: {e}")
        audit.log_error(run_id, str(e))
        audit.complete_run(run_id, status="failure", duration_seconds=time.time() - start_time)
        raise


def _save_query_as_note(question: str, result: QueryResult) -> Optional[Path]:
    """Save query result as a wiki note."""
    try:
        from ..services.wiki_repository import WikiRepository
        from datetime import datetime

        wiki_repo = WikiRepository()

        # Create note content
        content = f"""# Query: {question}

## Answer
{result.answer}

## Citations
"""
        for citation in result.citations:
            content += f"- [[{citation}]]\n"

        if result.coverage_gaps:
            content += "\n## Coverage Gaps\n"
            for gap in result.coverage_gaps:
                content += f"- {gap}\n"

        content += f"""
## Metadata
- **Query:** {question}
- **Generated:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
- **Confidence:** {result.confidence:.2f}
- **Citations:** {len(result.citations)}

---
*Generated by Veltiosi query workflow*
"""

        # Create safe filename
        safe_question = "".join(c if c.isalnum() or c in " -_" else "_" for c in question)
        safe_question = safe_question[:50]
        filename = f"Query - {safe_question}.md"

        # Determine path
        note_path = wiki_repo.vault_path / "queries" / filename
        note_path.parent.mkdir(parents=True, exist_ok=True)

        # Write note
        success = wiki_repo.write_note(note_path, content)
        if success:
            logger.info(f"Saved query as note: {note_path}")
            return note_path
        else:
            logger.error(f"Failed to save query note: {note_path}")
            return None

    except Exception as e:
        logger.error(f"Failed to save query as note: {e}")
        return None


def main():
    """Main entry point for wiki query workflow."""
    import argparse

    parser = argparse.ArgumentParser(description="Query your personal wiki")
    parser.add_argument(
        "question",
        nargs="?",
        help="Question to ask the wiki (optional for interactive mode)",
    )
    parser.add_argument(
        "--vault",
        type=Path,
        help="Path to Obsidian vault (default: from settings)",
    )
    parser.add_argument(
        "--max-notes",
        type=int,
        default=10,
        help="Maximum number of notes to use as context (default: 10)",
    )
    parser.add_argument(
        "--exclude-generated",
        action="store_true",
        help="Exclude generated notes from context",
    )
    parser.add_argument(
        "--interactive",
        "-i",
        action="store_true",
        help="Run in interactive mode",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Initialize workflow
    workflow = WikiQueryWorkflow(vault_path=args.vault)

    # Run query
    if args.interactive or not args.question:
        workflow.interactive_query()
    else:
        result = workflow.query(
            question=args.question,
            max_notes=args.max_notes,
            include_generated=not args.exclude_generated,
        )

        if result:
            print(result.answer)

            if result.citations:
                print("\nCitations:")
                for citation in result.citations:
                    print(f"- [[{citation}]]")

            if result.coverage_gaps:
                print("\nCoverage gaps identified:")
                for gap in result.coverage_gaps:
                    print(f"- {gap}")
        else:
            print("Failed to generate answer.")


if __name__ == "__main__":
    main()
