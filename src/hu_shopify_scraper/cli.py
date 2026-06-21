from __future__ import annotations

import asyncio
import builtins
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import List

import click
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from hu_shopify_scraper.db.models import Store
from hu_shopify_scraper.db.repository import Repository
from hu_shopify_scraper.discovery.app_reviews import discover_from_app_reviews
from hu_shopify_scraper.discovery.ct_logs import discover_ct
from hu_shopify_scraper.discovery.direct_search import discover_direct_search
from hu_shopify_scraper.discovery.google_dork import discover_via_bing, discover_via_google
from hu_shopify_scraper.discovery.hu_domains import discover_from_seed_list
from hu_shopify_scraper.discovery.hu_registry import discover_registry
from hu_shopify_scraper.discovery.onshopify_scraper import discover_onshopify
from hu_shopify_scraper.discovery.registry_historical import discover_registry_historical
from hu_shopify_scraper.discovery.sellercenter_scraper import discover_sellercenter
from hu_shopify_scraper.discovery.tranco import discover_tranco
from hu_shopify_scraper.verify.fingerprint import fingerprint_store
from hu_shopify_scraper.verify.metadata import extract_metadata

console = Console()
repo = Repository()


def async_run(coro):
    """Run a coroutine in a single-use event loop."""
    return asyncio.run(coro)


@click.group()
def cli() -> None:
    """Hungarian Shopify Store Scraper

    Discover and verify Shopify stores in Hungary.
    """
    repo.init_db()


@cli.command()
@click.option(
    "--google/--no-google",
    default=False,
    help="Use Google dorking to find candidates",
)
@click.option(
    "--seed/--no-seed",
    default=False,
    help="Check known Hungarian seed domains",
)
@click.option(
    "--ct/--no-ct",
    default=False,
    help="Discover via crt.sh certificate transparency logs (P0)",
)
@click.option(
    "--tranco/--no-tranco",
    default=False,
    help="Discover via Tranco top-1M .hu domains (P1a)",
)
@click.option(
    "--registry/--no-registry",
    default=False,
    help="Discover via .hu registry announcement list (P1b)",
)
@click.option(
    "--registry-historical/--no-registry-historical",
    default=False,
    help="Discover via Wayback-archived .hu registry lists (2021-present)",
)
@click.option(
    "--all",
    "all_flag",
    is_flag=True,
    default=False,
    help="Run all discovery strategies",
)
@click.option(
    "--onshopify/--no-onshopify",
    default=False,
    help="Discover via onshopify.com Hungary list",
)
@click.option(
    "--sellercenter/--no-sellercenter",
    default=False,
    help="Discover via sellercenter.io Hungary top stores",
)
@click.option(
    "--bing/--no-bing",
    default=False,
    help="Discover via Bing search (P2b)",
)
@click.option(
    "--reviews/--no-reviews",
    default=False,
    help="Discover via Shopify App Store reviews (config: app_review_slugs)",
)
@click.option(
    "--direct-search/--no-direct-search",
    default=False,
    help='Direct search for "Szolgáltató: Shopify" on Google + Bing',
)
@click.option(
    "--refresh",
    is_flag=True,
    default=False,
    help="Refresh cached data (crt.sh, Tranco, etc.)",
)
def discover(
    google: bool,
    seed: bool,
    ct: bool,
    tranco: bool,
    registry: bool,
    registry_historical: bool,
    all_flag: bool,
    onshopify: bool,
    sellercenter: bool,
    bing: bool,
    reviews: bool,
    direct_search: bool,
    refresh: bool,
) -> None:
    """Discover Hungarian Shopify store candidates."""

    if all_flag:
        google = seed = ct = tranco = registry = True
        registry_historical = onshopify = sellercenter = bing = True
        reviews = direct_search = True

    async def _discover() -> List[str]:
        candidates: list[str] = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            if google:
                task = progress.add_task(
                    "Searching via Google dorking...", total=None
                )
                try:
                    google_domains = await discover_via_google()
                    candidates.extend(google_domains)
                finally:
                    progress.remove_task(task)

            if seed:
                task = progress.add_task(
                    "Checking seed domains...", total=None
                )
                try:
                    seed_domains = await discover_from_seed_list()
                    candidates.extend(seed_domains)
                finally:
                    progress.remove_task(task)

        return builtins.list(dict.fromkeys(candidates))

    run_id = repo.start_run("discover")
    new_count = 0

    if any([google, seed, bing]):
        unique_candidates = async_run(_discover())

        if bing:
            console.print(
                "\n[bold blue]Running Bing dorking (P2b)...[/bold blue]"
            )
            bing_domains = async_run(discover_via_bing())
            for d in bing_domains:
                if d not in unique_candidates:
                    unique_candidates.append(d)

        if unique_candidates:
            console.print(
                f"\n[bold green]Found {len(unique_candidates)} "
                f"candidate domains.[/bold green]"
            )

            for domain in unique_candidates:
                if not repo.store_exists(domain):
                    store = Store(
                        domain=domain,
                        discovered_by="discover",
                        is_verified=False,
                        first_seen=datetime.now(),
                        last_verified=datetime.now(),
                    )
                    repo.upsert_store(store)
                    new_count += 1

            console.print(
                f"[green]Stored {new_count} new domains "
                f"in database.[/green]"
            )

    if ct:
        console.print(
            "\n[bold blue]Running CT log discovery (P0)...[/bold blue]"
        )
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TextColumn("{task.fields[stats]}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                "CT logs", total=0, stats=""
            )

            def ct_cb(phase, checked, total, found, errors):
                progress.update(
                    task,
                    total=total,
                    completed=checked,
                    description=f"CT [{phase}]",
                    stats=f"found {found}  errors {errors}",
                )

            ct_new = async_run(
                discover_ct(refresh=refresh, progress_callback=ct_cb)
            )
        new_count += ct_new
        console.print(
            f"[green]CT discovery found {ct_new} new "
            f"verified stores.[/green]"
        )

    if tranco:
        console.print(
            "\n[bold blue]Running Tranco discovery (P1a)...[/bold blue]"
        )
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TextColumn("{task.fields[stats]}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                "Tranco", total=0, stats=""
            )

            def tranco_cb(phase, checked, total, found, errors):
                progress.update(
                    task,
                    total=total,
                    completed=checked,
                    description=f"Tranco [{phase}]",
                    stats=f"found {found}  errors {errors}",
                )

            tranco_new = async_run(
                discover_tranco(refresh=refresh, progress_callback=tranco_cb)
            )
        new_count += tranco_new
        console.print(
            f"[green]Tranco discovery found {tranco_new} new "
            f"verified stores.[/green]"
        )

    if registry:
        console.print(
            "\n[bold blue]Running .hu registry discovery (P1b)...[/bold blue]"
        )
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TextColumn("{task.fields[stats]}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                "Registry", total=0, stats=""
            )

            def registry_cb(phase, checked, total, found, errors):
                progress.update(
                    task,
                    total=total,
                    completed=checked,
                    description=f"Registry [{phase}]",
                    stats=f"found {found}  errors {errors}",
                )

            registry_new = async_run(
                discover_registry(progress_callback=registry_cb)
            )
        new_count += registry_new
        console.print(
            f"[green]Registry discovery found {registry_new} new "
            f"verified stores.[/green]"
        )

    if registry_historical:
        console.print(
            "\n[bold blue]Running historical registry discovery "
            "(Wayback snapshots 2021-present)...[/bold blue]"
        )
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TextColumn("{task.fields[stats]}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                "Registry (historical)", total=0, stats=""
            )

            def rh_cb(phase, checked, total, found, errors):
                progress.update(
                    task,
                    total=total,
                    completed=checked,
                    description=f"RegistryHist [{phase}]",
                    stats=f"found {found}  errors {errors}",
                )

            rh_new = async_run(
                discover_registry_historical(progress_callback=rh_cb)
            )
        new_count += rh_new
        console.print(
            f"[green]Historical registry discovery found {rh_new} new "
            f"verified stores.[/green]"
        )

    if onshopify:
        console.print(
            "\n[bold blue]Running onshopify.com discovery...[/bold blue]"
        )
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TextColumn("{task.fields[stats]}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                "Onshopify", total=0, stats=""
            )

            def onshopify_cb(phase, checked, total, found, errors):
                progress.update(
                    task,
                    total=total,
                    completed=checked,
                    description=f"Onshopify [{phase}]",
                    stats=f"found {found}  errors {errors}",
                )

            onshopify_new = async_run(
                discover_onshopify(progress_callback=onshopify_cb)
            )
        new_count += onshopify_new
        console.print(
            f"[green]Onshopify discovery found {onshopify_new} new "
            f"verified stores.[/green]"
        )

    if sellercenter:
        console.print(
            "\n[bold blue]Running sellercenter.io discovery...[/bold blue]"
        )
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TextColumn("{task.fields[stats]}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                "SellerCenter", total=0, stats=""
            )

            def sellercenter_cb(phase, checked, total, found, errors):
                progress.update(
                    task,
                    total=total,
                    completed=checked,
                    description=f"SellerCenter [{phase}]",
                    stats=f"found {found}  errors {errors}",
                )

            sellercenter_new = async_run(
                discover_sellercenter(progress_callback=sellercenter_cb)
            )
        new_count += sellercenter_new
        console.print(
            f"[green]SellerCenter discovery found {sellercenter_new} new "
            f"verified stores.[/green]"
        )

    if reviews:
        console.print(
            "\n[bold blue]Running App Store reviews discovery...[/bold blue]"
        )
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TextColumn("{task.fields[stats]}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                "App Reviews", total=0, stats=""
            )

            def reviews_cb(phase, checked, total, found, errors):
                progress.update(
                    task,
                    total=total,
                    completed=checked,
                    description=f"Reviews [{phase}]",
                    stats=f"found {found}  errors {errors}",
                )

            reviews_new = async_run(
                discover_from_app_reviews(progress_callback=reviews_cb)
            )
        new_count += reviews_new
        console.print(
            f"[green]App Reviews discovery found {reviews_new} new "
            f"verified stores.[/green]"
        )

    if direct_search:
        console.print(
            '\n[bold blue]Running direct search'
            ' "Szolgáltató: Shopify"'
            ' (Google via real Chrome)...[/bold blue]'
        )
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TextColumn("{task.fields[stats]}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                "Direct search", total=0, stats=""
            )
            current_phase: dict[str, str] = {"phase": ""}

            def ds_cb(phase, checked, total, found, errors):
                current_phase["phase"] = phase
                progress.update(
                    task,
                    total=total if total else 1,
                    completed=checked,
                    description=f"Direct [{phase}]",
                    stats=(
                        f"found {found}  errors {errors}  "
                        f"checked {checked}/{total}"
                    ),
                )

            ds_new = async_run(
                discover_direct_search(progress_callback=ds_cb)
            )
        new_count += ds_new
        console.print(
            f"[green]Direct search found {ds_new} new "
            f"verified stores.[/green]"
        )

    repo.finish_run(run_id, 0, new_count, 0)
    console.print(
        f"\n[bold]Total new stores found: {new_count}[/bold]"
    )


@cli.command()
@click.option(
    "--limit",
    default=50,
    help="Max number of stores to verify",
)
@click.option(
    "--reverify/--no-reverify",
    default=False,
    help="Re-verify already verified stores",
)
def verify(limit: int, reverify: bool) -> None:
    """Verify candidates and extract metadata."""
    stores = repo.get_unverified_stores()
    if reverify:
        stores = repo.get_all_stores(verified_only=False)

    to_verify = stores[:limit]

    if not to_verify:
        console.print("[yellow]No stores to verify.[/yellow]")
        return

    console.print(f"Verifying [bold]{len(to_verify)}[/bold] stores...")

    run_id = repo.start_run("verify")

    async def _verify_all() -> None:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TextColumn("{task.fields[stats]}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                "Verifying stores...",
                total=len(to_verify),
                stats="",
            )

            verified_count = 0
            for i, store in enumerate(to_verify):
                progress.update(
                    task,
                    description=f"Checking {store.domain}",
                    stats=f"verified {verified_count}/{i}",
                )

                fp_result = await fingerprint_store(store.domain)

                if fp_result.is_shopify:
                    metadata = await extract_metadata(store.domain)

                    store.is_verified = True
                    store.last_verified = datetime.now()
                    store.store_name = (
                        metadata.get("store_name") or store.store_name
                    )
                    store.currency = (
                        metadata.get("currency") or store.currency
                    )
                    store.locale = metadata.get("locale") or store.locale
                    store.email = metadata.get("email") or store.email
                    store.phone = metadata.get("phone") or store.phone
                    store.description = (
                        metadata.get("description") or store.description
                    )
                    store.category = (
                        metadata.get("category") or store.category
                    )
                    store.myshopify_domain = (
                        fp_result.myshopify_domain or store.myshopify_domain
                    )

                    repo.upsert_store(store)
                    verified_count += 1

                progress.advance(task)

            console.print(
                f"\n[green]Verified {verified_count}/{len(to_verify)} "
                f"as Shopify stores.[/green]"
            )

    async_run(_verify_all())
    repo.finish_run(run_id, len(to_verify), 0, 0)


@cli.command(name="list")
@click.option("--verified/--all", "verified_only", default=True)
def list_stores(verified_only: bool) -> None:
    """List stored Shopify stores."""
    stores = repo.get_all_stores(verified_only=verified_only)

    if not stores:
        console.print("[yellow]No stores in database.[/yellow]")
        return

    table = Table(title=f"Hungarian Shopify Stores ({len(stores)})")
    table.add_column("Domain", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Merchant", style="dim")
    table.add_column("Currency", style="yellow")
    table.add_column("Category", style="magenta")
    table.add_column("Status", style="bold")

    for s in stores:
        status_parts = []
        if s.is_verified:
            status_parts.append("[green]Verified[/green]")
        else:
            status_parts.append("[yellow]Unverified[/yellow]")
        if s.needs_domain_resolution:
            status_parts.append("[red]Needs URL[/red]")
        status = " ".join(status_parts)

        table.add_row(
            s.domain,
            s.store_name or "-",
            s.merchant_name or "-",
            s.currency or "-",
            s.category or "-",
            status,
        )

    console.print(table)


@cli.command()
@click.argument("output", type=click.Path(), default="export.csv")
@click.option("--format", "fmt", type=click.Choice(["csv", "json"]), default="csv")
def export(output: str, fmt: str) -> None:
    """Export stores to CSV or JSON."""
    stores = repo.get_all_stores(verified_only=True)

    if not stores:
        console.print("[yellow]No verified stores to export.[/yellow]")
        return

    path = Path(output)

    if fmt == "csv":
        with path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "domain",
                    "store_name",
                    "currency",
                    "locale",
                    "email",
                    "phone",
                    "category",
                    "description",
                    "is_verified",
                    "first_seen",
                ]
            )
            for s in stores:
                writer.writerow(
                    [
                        s.domain,
                        s.store_name or "",
                        s.currency or "",
                        s.locale or "",
                        s.email or "",
                        s.phone or "",
                        s.category or "",
                        s.description or "",
                        "Yes" if s.is_verified else "No",
                        s.first_seen.isoformat() if s.first_seen else "",
                    ]
                )
    else:
        data = []
        for s in stores:
            data.append(
                {
                    "domain": s.domain,
                    "store_name": s.store_name,
                    "currency": s.currency,
                    "locale": s.locale,
                    "email": s.email,
                    "phone": s.phone,
                    "category": s.category,
                    "description": s.description,
                    "is_verified": s.is_verified,
                    "first_seen": (
                        s.first_seen.isoformat() if s.first_seen else None
                    ),
                }
            )
        with path.open("w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    console.print(f"[green]Exported {len(stores)} stores to {path}[/green]")


@cli.command()
@click.option("--count", default=5, type=int)
def stats(count: int) -> None:
    """Show database statistics."""
    total = repo.get_count(verified_only=False)
    verified = repo.get_count(verified_only=True)
    unverified = total - verified

    console.print("[bold]Database Statistics[/bold]")
    console.print(f"  Total stores:    {total}")
    console.print(f"  Verified:        {verified}")
    console.print(f"  Unverified:      {unverified}")
    console.print()

    if verified:
        source_counts = repo.get_counts_by_source()
        if source_counts:
            console.print("[bold]By Source[/bold]")
            for source, cnt in sorted(
                source_counts.items(), key=lambda x: -x[1]
            ):
                console.print(f"  {source:<14} {cnt}")
            console.print()

        console.print("[bold]Most Recent Verified Stores[/bold]")
        stores = repo.get_all_stores(verified_only=True)
        for s in stores[-count:]:
            console.print(f"  {s.domain}  ({s.store_name or 'N/A'})")


if __name__ == "__main__":
    cli()
