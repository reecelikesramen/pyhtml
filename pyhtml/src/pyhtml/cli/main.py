"""Main CLI entry point."""
import click
from pathlib import Path


@click.group()
@click.version_option()
def cli():
    """PyHTML framework CLI."""
    pass


@cli.command()
@click.option('--host', default='127.0.0.1', help='Host to bind to')
@click.option('--port', default=3000, type=int, help='Port to bind to')
@click.option('--reload', is_flag=True, help='Enable auto-reload')
@click.option('--pages-dir', default='pages', help='Directory containing .pyhtml files')
@click.option('--webtransport/--no-webtransport', default=None, help='Enable/disable WebTransport (HTTP/3)')
@click.pass_context
def dev(ctx, host, port, reload, pages_dir, webtransport):
    """Start development server."""
    # Check if defaults are being used, and if so, check config file
    from pyhtml.config import load_config
    
    # Check context.parameter_source to see if args were provided via CLI
    # If not provided via CLI, check config file
    config_defaults = load_config()
    
    if config_defaults:
        # We only want to apply config defaults if the value is currently the default
        # AND the user didn't explicitly provide it via CLI.
        # However, click validation happens before this.
        # A clearer way is to update defaults before parsing? No, too late.
        
        # Click's recommended way: context.default_map
        # But we are already inside the command.
        # We can just check parameter source.
        
        for param in ctx.command.params:
             name = param.name
             if name in config_defaults:
                 # Check if user provided this arg
                 if ctx.get_parameter_source(name) == click.core.ParameterSource.DEFAULT:
                     # Modify local variable for the function execution
                     if name == 'host': host = config_defaults[name]
                     if name == 'port': port = config_defaults[name]
                     if name == 'reload': reload = config_defaults[name]
                     if name == 'pages_dir': pages_dir = config_defaults[name]
                     if name == 'webtransport': webtransport = config_defaults[name]
    
    import asyncio
    from pyhtml.runtime.dev_server import run_dev_server

    click.echo(f"🚀 Starting PyHTML dev server on http://{host}:{port}")

    asyncio.run(run_dev_server(
        host=host,
        port=port,
        reload=reload,
        pages_dir=Path(pages_dir),
        enable_webtransport=webtransport
    ))


@cli.command()
@click.option('--optimize', is_flag=True, help='Optimize output')
@click.option('--pages-dir', default='pages', help='Directory containing .pyhtml files')
def build(optimize, pages_dir):
    """Build for production."""
    from pyhtml.compiler.build import build_project

    click.echo("📦 Building project...")
    build_project(optimize=optimize, pages_dir=Path(pages_dir))
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
@click.option('--pages-dir', default='pages', help='Directory containing .pyhtml files')
def validate(pages_dir):
    """Validate all .pyhtml files."""
    from pyhtml.cli.validate import validate_project

    click.echo("🔍 Validating project...")
    errors = validate_project(pages_dir=Path(pages_dir))

    if errors:
        click.echo(f"❌ Found {len(errors)} errors")
        for error in errors:
            click.echo(f"  {error}")
        raise click.Abort()
    else:
        click.echo("✅ No errors found")
