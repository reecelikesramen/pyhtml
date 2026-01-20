"""Main CLI entry point."""
import click
from pathlib import Path
from pyhtml.config import PyHTMLConfig, config as global_config


@click.group()
@click.version_option()
def cli():
    """PyHTML framework CLI."""
    pass


@cli.command()
@click.option('--host', default=None, help='Host to bind to')
@click.option('--port', default=None, type=int, help='Port to bind to')
@click.option('--reload', is_flag=True, help='Enable auto-reload')
@click.option('--pages-dir', default=None, help='Directory containing .pyhtml files')
def dev(host, port, reload, pages_dir):
    """Start development server."""
    import asyncio
    from pyhtml.runtime.dev_server import run_dev_server

    # Load config
    # We load config first, then override with CLI args if present
    loaded_config = PyHTMLConfig.load()
    
    # Merge CLI args
    final_host = host or "127.0.0.1"
    final_port = port or 3000
    # Update global config (so other modules can see it if needed)
    for field in loaded_config.__dataclass_fields__:
        setattr(global_config, field, getattr(loaded_config, field))
    
    # Override pages_dir if CLI arg provided
    if pages_dir:
        global_config.pages_dir = Path(pages_dir)
        
    final_pages_dir = global_config.pages_dir

    click.echo(f"🚀 Starting PyHTML dev server on http://{final_host}:{final_port}")
    click.echo(f"📂 Serving pages from: {final_pages_dir}")

    asyncio.run(run_dev_server(
        host=final_host,
        port=final_port,
        reload=reload,
        pages_dir=final_pages_dir
    ))


@cli.command()
@click.option('--optimize', is_flag=True, help='Optimize output')
@click.option('--pages-dir', default=None, help='Directory containing .pyhtml files')
def build(optimize, pages_dir):
    """Build for production."""
    from pyhtml.compiler.build import build_project

    # Load config
    loaded_config = PyHTMLConfig.load()
    final_pages_dir = Path(pages_dir) if pages_dir else loaded_config.pages_dir
    
    global_config.pages_dir = final_pages_dir

    click.echo("📦 Building project...")
    click.echo(f"📂 Pages directory: {final_pages_dir}")
    build_project(optimize=optimize, pages_dir=final_pages_dir)
    click.echo("✅ Build complete")


@cli.command()
@click.argument('type', type=click.Choice(['page', 'component']))
@click.argument('name')
def generate(type, name):
    """Generate a new page or component."""
    from pyhtml.cli.generators import generate_page, generate_component

    if type == 'page':
        generate_page(name)
    elif type == 'component':
        generate_component(name)

    click.echo(f"✅ Generated {type}: {name}")


@cli.command()
@click.option('--pages-dir', default=None, help='Directory containing .pyhtml files')
def validate(pages_dir):
    """Validate all .pyhtml files."""
    from pyhtml.cli.validate import validate_project

    loaded_config = PyHTMLConfig.load()
    final_pages_dir = Path(pages_dir) if pages_dir else loaded_config.pages_dir

    click.echo("🔍 Validating project...")
    errors = validate_project(pages_dir=final_pages_dir)

    if errors:
        click.echo(f"❌ Found {len(errors)} errors")
        for error in errors:
            click.echo(f"  {error}")
        raise click.Abort()
    else:
        click.echo("✅ No errors found")
