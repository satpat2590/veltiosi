"""Wiki query workflow."""

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..audit import AuditLogger
from ..indexing.jev_router import JevQueryRouter
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
        self.router = JevQueryRouter()

    def _route_and_retrieve(self, question: str, max_notes: int):
        """Jev-route the query; return (route, narrowed + reranked notes)."""
        route = self.router.route(question)
        logger.info(
            f"Jev route: intent={route.intent} domain={route.domain} "
            f"source={route.data_source} answerable={route.answerable} ({route.source})"
        )
        notes = self.retrieval.retrieve_for_query(
            query=question,
            category_filter=route.category_filter,
            max_notes=max_notes * 2,
        )
        # Jev semantic re-rank (fail-open: trim to max_notes when Jev is absent).
        if route.available and notes:
            items = [
                {
                    "id": str(n.path),
                    "title": n.title,
                    "snippet": (self.wiki_repo.read_note_content(str(n.path)) or "")[:400],
                }
                for n in notes
            ]
            ranked = self.router.rerank(question, items, top_k=max_notes)
            order = {r["id"]: r["jscore"] for r in ranked}
            notes = [n for n in notes if str(n.path) in order]
            notes.sort(key=lambda n: -order.get(str(n.path), 0.0))
        else:
            notes = notes[:max_notes]
        return route, notes

    def _answer(self, question: str, route, notes) -> Optional[QueryResult]:
        """Route the query to the right handler given the route + notes."""
        # Non-vault source wins over everything: a WHOOP/Edoras/Itihasa query will
        # naturally have no vault notes, so route it to its connector first.
        if route.available and route.data_source not in ("vault", "uncertain"):
            from ..connectors.datasources import query_source

            text = query_source(route.data_source, question)
            if text:
                return QueryResult(
                    answer=text,
                    citations=[],
                    confidence=route.intent_confidence or 0.5,
                    coverage_gaps=[],
                    suggested_new_notes=[],
                )
            return QueryResult(
                answer=(
                    f"This question looks like it needs the '{route.data_source}' data "
                    f"source (domain: {route.domain or 'unknown'}), but that source is unreachable."
                ),
                citations=[],
                confidence=route.intent_confidence or 0.5,
                coverage_gaps=[],
                suggested_new_notes=[],
            )
        if not notes:
            return QueryResult(
                answer="No relevant information found in the wiki.",
                citations=[],
                confidence=0.0,
                coverage_gaps=[f"No notes found related to: {question}"],
                suggested_new_notes=[],
            )
        if route.available and route.intent == "clarify":
            return QueryResult(
                answer=f"Can you clarify? I read this as a {route.domain or 'general'} question but it's underspecified.",
                citations=[],
                confidence=route.intent_confidence or 0.4,
                coverage_gaps=[],
                suggested_new_notes=[],
            )
        if route.available and route.intent in ("fact_lookup", "navigation"):
            parts = []
            for note in notes[:3]:
                content = self.wiki_repo.read_note_content(str(note.path)) or ""
                parts.append(f"## {note.title}\n{content[:400]}")
            return QueryResult(
                answer="\n\n".join(parts) or "No content found.",
                citations=[f"[[{note.title}]]" for note in notes[:3]],
                confidence=route.intent_confidence or 0.7,
                coverage_gaps=[],
                suggested_new_notes=[],
            )
        # Synthesis (or Jev absent) -> Gemini.
        result = llm_service.generate_query_answer(
            question=question,
            wiki_context=self._build_wiki_context(notes),
        )
        if result:
            logger.info(f"Generated answer with {len(result.citations)} citations")
        else:
            logger.error("Failed to generate answer")
        return result

    def search(
        self,
        question: str,
        max_notes: int = 10,
        include_generated: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """Rich search (UI): routing decision + ranked notes + answer."""
        route, notes = self._route_and_retrieve(question, max_notes)
        result = self._answer(question, route, notes)
        if result is None:
            return None
        note_dicts = [
            {
                "title": n.title,
                "path": str(n.path),
                "domain_folder": n.domain_folder,
                "root_category": n.primary_root_category.value if n.primary_root_category else None,
                "note_type": n.note_type.value if n.note_type else None,
                "subcategories": list(n.subcategories),
                "snippet": (self.wiki_repo.read_note_content(str(n.path)) or "")[:400],
            }
            for n in notes
        ]
        return {
            "route": {
                "available": route.available,
                "source": route.source,
                "intent": route.intent,
                "intent_confidence": route.intent_confidence,
                "domain": route.domain,
                "secondary_domains": route.secondary_domains,
                "data_source": route.data_source,
                "answerable": route.answerable,
            },
            "notes": note_dicts,
            "result": result,
        }

    def query(
        self,
        question: str,
        max_notes: int = 10,
        include_generated: bool = True,
    ) -> Optional[QueryResult]:
        """Query the wiki (classic entry point) — returns just the QueryResult."""
        out = self.search(question, max_notes, include_generated)
        return out["result"] if out else None

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
