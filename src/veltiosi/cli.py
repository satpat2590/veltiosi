"""CLI interface for Veltiosi."""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from veltiosi import __version__
from veltiosi.settings import settings

app = typer.Typer(
    name="veltiosi",
    help="Automation layer for the Obsidian knowledge base",
    add_completion=False,
)

console = Console()


@app.callback()
def callback(
    version: Optional[bool] = typer.Option(None, "--version", "-v", help="Show version and exit"),
) -> None:
    """Veltiosi: Automation layer for the Obsidian knowledge base."""
    if version:
        console.print(f"Veltiosi v{__version__}")
        raise typer.Exit()


@app.command()
def wiki_index(
    full: bool = typer.Option(False, "--full", help="Regenerate index from scratch"),
    check: bool = typer.Option(False, "--check", help="Check index consistency without writing"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be done without writing"
    ),
) -> None:
    """Generate or update wiki index and category MOCs."""
    from veltiosi.workflows.wiki_index import run_index

    if dry_run:
        console.print("[yellow]Dry run mode - no changes will be written[/yellow]")

    try:
        result = run_index(
            full=full,
            check=check,
            dry_run=dry_run,
        )

        if json_output:
            console.print_json(data=result)
        else:
            console.print(f"[green]✓ Index operation completed[/green]")
            if check:
                if result.get("consistent", True):
                    console.print("[green]✓ Index is consistent[/green]")
                else:
                    console.print("[red]✗ Index inconsistencies found[/red]")
                    for issue in result.get("issues", []):
                        console.print(f"  - {issue}")

    except Exception as e:
        console.print(f"[red]✗ Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def wiki_lint(
    report: bool = typer.Option(False, "--report", help="Generate detailed lint report"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    fix_safe: bool = typer.Option(False, "--fix-safe", help="Apply safe fixes automatically"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be fixed without writing"
    ),
) -> None:
    """Lint the wiki for health and consistency issues."""
    from veltiosi.workflows.wiki_lint import run_lint

    if dry_run:
        console.print("[yellow]Dry run mode - no changes will be written[/yellow]")

    try:
        result = run_lint(
            report=report,
            fix_safe=fix_safe,
            dry_run=dry_run,
        )

        if json_output:
            console.print_json(data=result)
        else:
            issues = result.get("issues", [])
            if issues:
                table = Table(title="Lint Issues")
                table.add_column("Severity", style="bold")
                table.add_column("Note")
                table.add_column("Issue")
                table.add_column("Suggestion")

                for issue in issues:
                    severity_style = {
                        "error": "red",
                        "warning": "yellow",
                        "info": "blue",
                    }.get(issue["severity"], "white")
                    table.add_row(
                        f"[{severity_style}]{issue['severity']}[/{severity_style}]",
                        str(issue["note_path"]),
                        issue["message"],
                        issue.get("suggestion", ""),
                    )

                console.print(table)
                console.print(f"[yellow]Found {len(issues)} issues[/yellow]")
            else:
                console.print("[green]✓ No lint issues found[/green]")

    except Exception as e:
        console.print(f"[red]✗ Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def wiki_ingest(
    source: str = typer.Argument(..., help="Path to local file or URL"),
    source_type: Optional[str] = typer.Option(
        None, "--type", help="Source type (article, paper, book, video, podcast, data, receipt)"
    ),
    domain: Optional[str] = typer.Option(None, "--domain", help="Target domain folder"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be done without writing"
    ),
) -> None:
    """Ingest a raw source into the wiki."""
    from veltiosi.workflows.wiki_ingest import run_ingest

    if dry_run:
        console.print("[yellow]Dry run mode - no changes will be written[/yellow]")

    try:
        result = run_ingest(
            source=source,
            source_type=source_type,
            domain=domain,
            dry_run=dry_run,
        )

        if "error" in result:
            console.print(f"[red]✗ {result['error']}[/red]")
            raise typer.Exit(1)

        console.print(f"[green]✓ Ingest operation completed[/green]")
        console.print(f"  Source: {result.get('source_title')}")
        console.print(f"  Summary note: {result.get('summary_note_path')}")
        console.print(f"  Pages to update: {len(result.get('pages_to_update', []))}")

    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]✗ Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def task_sync(
    days: int = typer.Option(7, "--days", help="Number of days of completions to sync"),
    task_id: Optional[int] = typer.Option(None, "--task-id", help="Sync specific task ID"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be done without writing"
    ),
) -> None:
    """Sync Atma task completions to wiki compounding pages."""
    from veltiosi.workflows.task_sync import run_task_sync

    if dry_run:
        console.print("[yellow]Dry run mode - no changes will be written[/yellow]")

    try:
        result = run_task_sync(
            days=days,
            task_id=task_id,
            dry_run=dry_run,
        )

        if json_output:
            console.print_json(data=result)
        else:
            console.print(f"[green]✓ Task sync completed[/green]")
            console.print(f"  Tasks processed: {result.get('tasks_processed', 0)}")
            console.print(f"  Auto-applied: {result.get('auto_applied', 0)}")
            console.print(f"  Review queue items: {result.get('review_items_created', 0)}")
            console.print(f"  Skipped: {result.get('skipped', 0)}")

            if result.get("review_items_created", 0) > 0:
                console.print("\n[yellow]Review queue items created:[/yellow]")
                for item in result.get("review_queue_items", []):
                    console.print(f"  - {item}")

    except Exception as e:
        console.print(f"[red]✗ Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def weekly_synthesis(
    week: Optional[str] = typer.Option(
        None, "--week", help="Week in YYYY-WW format (default: current week)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be done without writing"
    ),
) -> None:
    """Generate weekly synthesis note."""
    from veltiosi.workflows.weekly_synthesis import run_weekly_synthesis

    if dry_run:
        console.print("[yellow]Dry run mode - no changes will be written[/yellow]")

    try:
        result = run_weekly_synthesis(
            week=week,
            dry_run=dry_run,
        )

        if json_output:
            console.print_json(data=result)
        else:
            console.print(f"[green]✓ Weekly synthesis generated[/green]")
            console.print(f"  Output: {result.get('output_path')}")
            console.print(f"  Category balance analyzed: {len(result.get('category_balance', {}))}")
            console.print(f"  Gaps identified: {len(result.get('gaps', []))}")

    except Exception as e:
        console.print(f"[red]✗ Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def wiki_query(
    question: str = typer.Argument(..., help="Question to answer"),
    category: Optional[str] = typer.Option(
        None, "--category", help="Limit to specific root category"
    ),
    save_note: bool = typer.Option(False, "--save-note", help="Save answer as a new wiki note"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be done without writing"
    ),
) -> None:
    """Query the wiki with a question."""
    from veltiosi.workflows.wiki_query import run_query

    if dry_run:
        console.print("[yellow]Dry run mode - no changes will be written[/yellow]")

    try:
        result = run_query(
            question=question,
            category=category,
            save_note=save_note,
            dry_run=dry_run,
        )

        if json_output:
            console.print_json(data=result)
        else:
            console.print(f"[bold]Answer:[/bold]")
            console.print(result.get("answer", ""))
            console.print(f"\n[bold]Citations:[/bold]")
            for citation in result.get("citations", []):
                console.print(f"  - {citation}")

            if result.get("coverage_gaps"):
                console.print(f"\n[yellow]Coverage gaps:[/yellow]")
                for gap in result.get("coverage_gaps", []):
                    console.print(f"  - {gap}")

    except Exception as e:
        console.print(f"[red]✗ Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def jev_classify(
    folder: Optional[str] = typer.Option(
        None, "--folder", help="Restrict to a domain folder (e.g. \"Satya's Roamings\")"
    ),
    limit: Optional[int] = typer.Option(None, "--limit", help="Max notes to classify"),
    threshold: float = typer.Option(
        0.55, "--threshold", help="Confidence threshold for auto-apply (root)"
    ),
    workers: int = typer.Option(16, "--workers", help="Concurrent classification requests"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Classify notes with Jev (System One) — calibrated + confidence-aware, read-only."""
    from veltiosi.workflows.jev_classify import run_jev_classify

    try:
        result = run_jev_classify(
            folder=folder, limit=limit, threshold=threshold, workers=workers
        )
    except Exception as e:
        console.print(f"[red]✗ Error: {e}[/red]")
        raise typer.Exit(1)

    if "error" in result:
        console.print(f"[yellow]⚠ {result['error']}[/yellow]")
        raise typer.Exit(1)

    if json_output:
        console.print_json(data=result)
        return

    console.print(
        f"[green]✓ Jev classified {result['classified']} notes "
        f"({result['available']} available)[/green]"
    )
    console.print(
        f"  Confident root (≥{result['threshold']}): {result['confident_root']}"
    )
    console.print(f"  Review / low-confidence: {result['review_count']}")

    console.print("\n[bold]Root distribution (Jev vs deterministic):[/bold]")
    root_table = Table(title="Root Category")
    root_table.add_column("Root", style="bold")
    root_table.add_column("Jev", justify="right")
    root_table.add_column("Deterministic", justify="right")
    root_dist = result.get("root_distribution", {})
    det_dist = result.get("deterministic_root_distribution", {})
    all_roots = sorted(set(root_dist) | set(det_dist))
    for root in all_roots:
        root_table.add_row(root, str(root_dist.get(root, 0)), str(det_dist.get(root, 0)))
    console.print(root_table)

    disagreements = result.get("disagreements", [])
    console.print(
        f"\n[yellow]Deterministic↔Jev disagreements: {result.get('disagreement_count', 0)}[/yellow]"
    )
    if disagreements:
        dtable = Table(title="Disagreements (deterministic root vs Jev root)")
        dtable.add_column("Note")
        dtable.add_column("Deterministic")
        dtable.add_column("Jev")
        dtable.add_column("Conf", justify="right")
        for d in disagreements[:30]:
            dtable.add_row(
                d["title"],
                d["deterministic_root"] or "-",
                d["root"] or "-",
                f"{d['root_confidence']:.2f}" if d["root_confidence"] is not None else "-",
            )
        console.print(dtable)

    review = result.get("review", [])
    if review:
        console.print(f"\n[yellow]Review queue ({len(review)}):[/yellow]")
        for r in review[:30]:
            conf = f"{r['root_confidence']:.2f}" if r["root_confidence"] is not None else "-"
            console.print(f"  - [{r['source']}] conf={conf}  {r['title']}")


@app.command()
def config_show() -> None:
    """Show current configuration."""
    console.print("[bold]Veltiosi Configuration[/bold]")
    console.print(f"Obsidian vault: {settings.obsidian_vault}")
    console.print(f"Audit directory: {settings.audit_dir}")

    console.print("\n[bold]Root Categories[/bold]")
    for name, config in settings.root_categories.items():
        console.print(f"  {name}: {config.display_name}")

    console.print("\n[bold]Subcategories[/bold]")
    for name, config in settings.subcategories.items():
        console.print(f"  {name}: {config.display_name} ({config.primary_root})")

    console.print(f"\n[bold]Task Rules[/bold]: {len(settings.task_rules)} rules")


@app.command()
def status() -> None:
    """Show system status."""
    from veltiosi.connectors.obsidian import ObsidianConnector

    connector = ObsidianConnector()
    note_count = connector.count_notes()

    console.print("[bold]Veltiosi Status[/bold]")
    console.print(f"Version: {__version__}")
    console.print(f"Obsidian vault: {settings.obsidian_vault}")
    console.print(f"Notes in vault: {note_count}")
    console.print(f"Root categories: {len(settings.root_categories)}")
    console.print(f"Subcategories: {len(settings.subcategories)}")
    console.print(f"Task rules: {len(settings.task_rules)}")

    # Check if vault exists
    if settings.obsidian_vault.exists():
        console.print("[green]✓ Vault exists[/green]")
    else:
        console.print("[red]✗ Vault not found[/red]")


@app.command()
def hermes_setup() -> None:
    """Set up Hermes integration."""
    from veltiosi.connectors.hermes import HermesConnector

    console.print("[bold]Setting up Hermes integration[/bold]")

    try:
        connector = HermesConnector()

        # Test Hermes connection
        test_results = connector.test_integration()

        console.print(f"Hermes home: {connector.hermes_home}")
        console.print(f"Hermes home exists: {'✓' if test_results['hermes_home_exists'] else '✗'}")
        console.print(
            f"Skills directory exists: {'✓' if test_results['skills_dir_exists'] else '✗'}"
        )
        console.print(
            f"Profiles directory exists: {'✓' if test_results['profiles_dir_exists'] else '✗'}"
        )

        if test_results["hermes_home_exists"]:
            console.print(f"Available skills: {len(test_results['available_skills'])}")
            console.print(f"Active profile: {test_results['active_profile'] or 'None'}")
            console.print(
                f"Veltiosi skill registered: {'✓' if test_results['veltiosi_skill_registered'] else '✗'}"
            )

            # Register Veltiosi skill if not already registered
            if not test_results["veltiosi_skill_registered"]:
                console.print("\n[yellow]Registering Veltiosi as Hermes skill...[/yellow]")
                if connector.register_veltiosi_skill():
                    console.print("[green]✓ Veltiosi skill registered[/green]")
                else:
                    console.print("[red]✗ Failed to register Veltiosi skill[/red]")

            # Create Veltiosi profile
            console.print("\n[yellow]Creating Veltiosi profile...[/yellow]")
            if connector.create_veltiosi_profile():
                console.print("[green]✓ Veltiosi profile created[/green]")
            else:
                console.print("[red]✗ Failed to create Veltiosi profile[/red]")

            # Setup cron jobs
            console.print("\n[yellow]Setting up cron jobs...[/yellow]")
            if connector.setup_cron_jobs():
                console.print("[green]✓ Cron jobs configured[/green]")
            else:
                console.print("[yellow]⚠ Cron jobs setup skipped (may need manual setup)[/yellow]")

            console.print("\n[bold]Hermes integration complete![/bold]")
            console.print("You can now use Veltiosi through Hermes with:")
            console.print("  hermes veltiosi <command> [args]")

        else:
            console.print("\n[yellow]Hermes not found at: {connector.hermes_home}[/yellow]")
            console.print("Please install Hermes or set HERMES_HOME environment variable")

    except Exception as e:
        console.print(f"[red]✗ Hermes setup failed: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def hermes_status() -> None:
    """Check Hermes integration status."""
    from veltiosi.connectors.hermes import HermesConnector

    console.print("[bold]Hermes Integration Status[/bold]")

    try:
        connector = HermesConnector()
        test_results = connector.test_integration()

        # Create status table
        from rich.table import Table

        table = Table(title="Hermes Integration")
        table.add_column("Component", style="bold")
        table.add_column("Status", style="bold")
        table.add_column("Details")

        table.add_row(
            "Hermes Home",
            "✓" if test_results["hermes_home_exists"] else "✗",
            str(connector.hermes_home),
        )

        table.add_row(
            "Skills Directory",
            "✓" if test_results["skills_dir_exists"] else "✗",
            str(connector.skills_dir),
        )

        table.add_row(
            "Profiles Directory",
            "✓" if test_results["profiles_dir_exists"] else "✗",
            str(connector.profiles_dir),
        )

        if test_results["hermes_home_exists"]:
            table.add_row(
                "Available Skills",
                str(len(test_results["available_skills"])),
                ", ".join(test_results["available_skills"][:5])
                + ("..." if len(test_results["available_skills"]) > 5 else ""),
            )

            table.add_row(
                "Active Profile",
                test_results["active_profile"] or "None",
                test_results["active_profile"] or "No active profile",
            )

            table.add_row(
                "Veltiosi Skill",
                "✓" if test_results["veltiosi_skill_registered"] else "✗",
                "Registered" if test_results["veltiosi_skill_registered"] else "Not registered",
            )

        console.print(table)

        # Recommendations
        if not test_results["hermes_home_exists"]:
            console.print("\n[yellow]Recommendations:[/yellow]")
            console.print("1. Install Hermes Agent")
            console.print("2. Set HERMES_HOME environment variable")
            console.print("3. Run 'veltiosi hermes-setup'")

        elif not test_results["veltiosi_skill_registered"]:
            console.print("\n[yellow]Recommendations:[/yellow]")
            console.print("Run 'veltiosi hermes-setup' to register Veltiosi skill")

    except Exception as e:
        console.print(f"[red]✗ Failed to check Hermes status: {e}[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
