from __future__ import annotations

import os

import typer

from jev_mcp.credentials import mask, remove_api_key, resolve_api_key, save_api_key, verify_api_key
from jev_mcp.errors import JevMcpError
from jev_mcp.util.paths import credentials_path

key_app = typer.Typer(name="key", help="Manage the TypeSafe API key used by jev-mcp")


@key_app.command("add")
def key_add(api_key: str = typer.Argument(..., help="TypeSafe API key")) -> None:
    """Verify the key against TypeSafe, then store it locally."""
    candidate = api_key.strip()
    try:
        verify_api_key(candidate)
    except JevMcpError as exc:
        typer.echo(f"[{exc.code}] {exc.message}", err=True)
        raise typer.Exit(code=1) from exc

    path = save_api_key(candidate)
    typer.echo(f"Key saved to {path}", err=True)
    if os.name != "posix":
        typer.echo(
            "Note: on Windows the file is protected only by your user profile ACL. "
            "On a shared machine prefer the TYPESAFE_API_KEY environment variable.",
            err=True,
        )
    typer.echo("Run 'jev-mcp key status' to confirm.", err=True)


@key_app.command("status")
def key_status() -> None:
    """Show where the key comes from, without revealing it."""
    api_key, source = resolve_api_key()
    if api_key is None:
        typer.echo("key: none")
        typer.echo(f"looked in: TYPESAFE_API_KEY, {credentials_path()}")
        return
    typer.echo(f"key: {mask(api_key)}")
    typer.echo(f"source: {source}")


@key_app.command("remove")
def key_remove() -> None:
    """Delete the locally stored key."""
    if remove_api_key():
        typer.echo("Key removed.", err=True)
        return
    typer.echo("No stored key to remove.", err=True)
