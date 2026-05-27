from __future__ import annotations
import typer
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

app = typer.Typer(name="aacr", help="Agentic API Capability Registry", add_completion=False)
console = Console()


@app.command()
def ingest(
    url: str = typer.Argument(..., help="URL of the Swagger/OpenAPI spec"),
    source_id: Optional[str] = typer.Option(None, "--source-id", help="Override source identifier"),
    org_id: str = typer.Option("default", "--org-id", help="Organisation namespace"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print capabilities without writing to stores"),
):
    """Ingest a Swagger/OpenAPI specification and register its capabilities."""
    from urllib.parse import urlparse
    from datetime import datetime, timezone
    from core.ingestion import fetch_spec, extract_base_url, extract_operations
    from core.extraction import build_capability
    from core.embeddings import embed_text, build_embedding_text
    from models.capability import IngestionSource
    import stores.mongo as mongo
    import stores.qdrant as qdrant
    import config

    if source_id is None:
        source_id = urlparse(url).netloc.replace(".", "_").replace("-", "_")

    console.print(f"\n[bold]Ingesting[/bold] {url}")
    console.print(f"  source_id=[cyan]{source_id}[/cyan]  org_id=[cyan]{org_id}[/cyan]  dry_run={dry_run}\n")

    if not dry_run:
        mongo.upsert_source(IngestionSource(source_id=source_id, org_id=org_id, url=url, status="pending"))

    with console.status("[bold blue]Fetching spec...[/bold blue]"):
        try:
            spec = fetch_spec(url)
        except RuntimeError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)

    base_url = extract_base_url(spec, url)
    operations = extract_operations(spec, base_url)
    console.print(f"Found [bold]{len(operations)}[/bold] operations  base_url=[dim]{base_url}[/dim]\n")

    llm_active = (
        config.LLM_PROVIDER == "ollama"
        or config.ANTHROPIC_API_KEY
        or config.OPENAI_API_KEY
    )
    provider_label = config.LLM_PROVIDER if llm_active else "none"
    if llm_active:
        console.print(f"LLM enrichment: [green]{provider_label}[/green]  model=[dim]{config.OLLAMA_MODEL if config.LLM_PROVIDER == 'ollama' else ''}[/dim]\n")
    else:
        console.print("[yellow]No LLM configured — using rule-based extraction only.[/yellow]\n")

    # ── extract capabilities ───────────────────────────────────────────────────
    capabilities = []
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as p:
        task = p.add_task("Extracting...", total=len(operations))
        for op in operations:
            p.update(task, description=f"[cyan]{op['method']:6}[/cyan] {op['path']}")
            capabilities.append(build_capability(op, source_id=source_id, org_id=org_id))
            p.advance(task)

    if dry_run:
        _print_capabilities_table(capabilities)
        console.print("\n[dim]Dry run — nothing written.[/dim]\n")
        return

    # ── embed + store ──────────────────────────────────────────────────────────
    with console.status("[bold blue]Loading embedding model...[/bold blue]"):
        # warm up model before the progress loop
        embed_text(capabilities[0].tool_name)

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as p:
        task = p.add_task("Storing...", total=len(capabilities))
        for cap in capabilities:
            p.update(task, description=f"[dim]{cap.tool_name}[/dim]")
            vector = embed_text(build_embedding_text(cap))
            mongo.upsert_capability(cap)
            qdrant.upsert_vector(
                cap.capability_id,
                vector,
                payload={
                    "org_id": cap.org_id,
                    "source_id": cap.source_id,
                    "domain": cap.domain,
                    "tool_name": cap.tool_name,
                },
            )
            p.advance(task)

    mongo.upsert_source(IngestionSource(
        source_id=source_id,
        org_id=org_id,
        url=url,
        status="done",
        capability_count=len(capabilities),
        ingested_at=datetime.now(timezone.utc),
    ))

    console.print(f"\n[green]Done.[/green] [bold]{len(capabilities)}[/bold] capabilities ingested from [cyan]{source_id}[/cyan].\n")


@app.command()
def status():
    """Show connection health and registry counts."""
    import stores.mongo as mongo
    import stores.qdrant as qdrant
    import config

    mongo_ok = mongo.ping()
    qdrant_ok = qdrant.ping()

    console.print()
    _status_row("MongoDB", mongo_ok, config.MONGO_URI)
    _status_row("Qdrant ", qdrant_ok, config.QDRANT_URL)

    if mongo_ok:
        caps = mongo.count_capabilities(config.DEFAULT_ORG_ID)
        srcs = mongo.count_sources(config.DEFAULT_ORG_ID)
        console.print(f"\n  Capabilities: [bold]{caps}[/bold]   Sources: [bold]{srcs}[/bold]   Org: [cyan]{config.DEFAULT_ORG_ID}[/cyan]")

    console.print()


@app.command()
def sources():
    """List all ingested API sources."""
    import stores.mongo as mongo
    import config

    srcs = mongo.list_sources(config.DEFAULT_ORG_ID)
    if not srcs:
        console.print("[dim]No sources ingested yet.[/dim]")
        return

    table = Table(title="Ingested Sources", show_lines=True)
    table.add_column("source_id", style="cyan")
    table.add_column("status")
    table.add_column("capabilities", justify="right")
    table.add_column("ingested_at")
    table.add_column("url", style="dim")

    for s in srcs:
        status_str = f"[green]{s.status}[/green]" if s.status == "done" else f"[yellow]{s.status}[/yellow]"
        ts = s.ingested_at.strftime("%Y-%m-%d %H:%M") if s.ingested_at else "—"
        table.add_row(s.source_id, status_str, str(s.capability_count), ts, s.url)

    console.print(table)


@app.command()
def flush(
    source: str = typer.Option(..., "--source", help="source_id to remove"),
    org_id: str = typer.Option("default", "--org-id"),
):
    """Remove all capabilities for a given source."""
    import stores.mongo as mongo
    import stores.qdrant as qdrant

    n = mongo.delete_by_source(source, org_id)
    qdrant.delete_by_source(source, org_id)
    console.print(f"Flushed [bold]{n}[/bold] capabilities for source [cyan]{source}[/cyan].")


@app.command()
def search(
    query: str = typer.Argument(..., help="Natural language query"),
    mode: str = typer.Option("curl", "--mode", help="curl | results"),
    top_k: int = typer.Option(5, "--top-k", help="Number of results to return"),
    org_id: str = typer.Option("default", "--org-id"),
):
    """Search capabilities using natural language."""
    from core.retrieval import search as do_search
    import config

    with console.status("[bold blue]Searching...[/bold blue]"):
        results = do_search(query, org_id=org_id, top_k=top_k)

    if not results:
        console.print("[yellow]No results found.[/yellow]")
        return

    if mode == "results":
        _print_results_mode(results[0])
        return

    console.print(f"\n  Query: [bold]{query}[/bold]   mode=[cyan]{mode}[/cyan]   org=[dim]{org_id}[/dim]\n")
    for r in results:
        cap = r.capability
        conf_color = "green" if r.score >= 0.85 else "yellow" if r.score >= 0.70 else "red"
        console.print(
            f"  [bold cyan]#{r.rank}[/bold cyan]  [bold]{cap.tool_name}[/bold]"
            f"   confidence: [{conf_color}]{r.score:.4f}[/{conf_color}]"
            f"   domain: [dim]{cap.domain}[/dim]"
        )
        console.print(f"       {cap.execution.method}  {cap.execution.path}")
        console.print(f"       [dim]{cap.description}[/dim]")
        console.print(f"       [green]{cap.execution.curl}[/green]")
        if cap.input_schema:
            params = ", ".join(f"{k}:{v.get('type','?')}" for k, v in cap.input_schema.items() if k != "body")
            if params:
                console.print(f"       input:  {params}")
        console.print()


@app.command("list")
def list_caps(
    domain: Optional[str] = typer.Option(None, "--domain", help="Filter by domain"),
    org_id: str = typer.Option("default", "--org-id"),
):
    """List all registered capabilities, optionally filtered by domain."""
    import stores.mongo as mongo

    caps = mongo.list_capabilities(org_id, domain=domain)
    if not caps:
        msg = f"No capabilities found for domain=[cyan]{domain}[/cyan]." if domain else "No capabilities ingested yet."
        console.print(msg)
        return

    title = f"Capabilities — domain: {domain}" if domain else "All Capabilities"
    table = Table(title=title, show_lines=False, box=None, pad_edge=False)
    table.add_column("tool_name", style="cyan", min_width=35)
    table.add_column("domain", min_width=12)
    table.add_column("method", justify="center", min_width=7)
    table.add_column("path")

    for cap in sorted(caps, key=lambda c: (c.domain, c.execution.method, c.tool_name)):
        safe_mark = "" if cap.operational_meta.safe else "[dim]✗[/dim]"
        table.add_row(cap.tool_name, cap.domain, cap.execution.method + safe_mark, cap.execution.path)

    console.print(table)
    console.print(f"\n  [dim]{len(caps)} capabilities[/dim]")


@app.command()
def inspect(
    tool_name: str = typer.Argument(..., help="tool_name to inspect"),
    org_id: str = typer.Option("default", "--org-id"),
):
    """Show full detail for a single capability."""
    import stores.mongo as mongo
    import json

    cap = mongo.get_capability_by_tool_name(tool_name, org_id)
    if not cap:
        console.print(f"[red]Not found:[/red] no capability with tool_name=[cyan]{tool_name}[/cyan]")
        raise typer.Exit(1)

    console.print()
    console.print(f"  [bold cyan]{cap.tool_name}[/bold cyan]   [dim]{cap.capability_id}[/dim]")
    console.print(f"  domain:      [bold]{cap.domain}[/bold]")
    console.print(f"  description: {cap.description}")
    if cap.intent_examples:
        console.print(f"  intent:      {' | '.join(cap.intent_examples)}")

    console.print()
    console.print(f"  [bold]Execution[/bold]")
    console.print(f"    method:   {cap.execution.method}")
    console.print(f"    path:     {cap.execution.path}")
    console.print(f"    base_url: [dim]{cap.execution.base_url}[/dim]")
    console.print(f"    curl:     [green]{cap.execution.curl}[/green]")

    console.print()
    console.print(f"  [bold]Operational metadata[/bold]")
    meta = cap.operational_meta
    console.print(
        f"    safe={meta.safe}  idempotent={meta.idempotent}"
        f"  requires_auth={meta.requires_auth}  destructive={meta.destructive}"
    )

    if cap.input_schema:
        console.print()
        console.print(f"  [bold]Input schema[/bold]")
        for name, schema in cap.input_schema.items():
            req = "[red]*[/red]" if schema.get("required") else ""
            console.print(f"    {req}{name}: {schema.get('type','?')}  ({schema.get('in','')})")

    if cap.response_fields:
        console.print()
        console.print(f"  [bold]Response fields[/bold]")
        console.print(f"    {', '.join(cap.response_fields)}")

    console.print()


# ── helpers ────────────────────────────────────────────────────────────────────


def _print_results_mode(result) -> None:
    from core.executor import execute
    cap = result.capability

    if not cap.operational_meta.safe:
        console.print(
            f"[yellow]Top match [bold]{cap.tool_name}[/bold] is {cap.execution.method} "
            f"(not safe). Returning curl instead.[/yellow]\n"
        )
        console.print(f"  [green]{cap.execution.curl}[/green]")
        return

    console.print(f"\n  Executing [bold]{cap.tool_name}[/bold]   confidence: [green]{result.score:.4f}[/green]\n")
    try:
        with console.status("[bold blue]Calling API...[/bold blue]"):
            payload = execute(cap)
        import json
        console.print_json(json.dumps(payload) if not isinstance(payload, str) else payload)
    except Exception as e:
        console.print(f"[red]Execution failed:[/red] {e}")



def _status_row(label: str, ok: bool, addr: str) -> None:
    state = "[green]connected[/green]" if ok else "[red]unreachable[/red]"
    console.print(f"  {label}  {state}   [dim]{addr}[/dim]")


def _print_capabilities_table(capabilities) -> None:
    table = Table(title="Extracted Capabilities (dry run)", show_lines=True)
    table.add_column("tool_name", style="cyan")
    table.add_column("domain")
    table.add_column("method", justify="center")
    table.add_column("path")
    table.add_column("description")

    for cap in capabilities:
        desc = cap.description
        if len(desc) > 65:
            desc = desc[:62] + "..."
        table.add_row(cap.tool_name, cap.domain, cap.execution.method, cap.execution.path, desc)

    console.print(table)


if __name__ == "__main__":
    app()
