---
name: Setup Guide
description: Instructions for setting up the environment using `scripts/` and `uv`.
---

# Setup Guide for PyWire

This guide covers how to set up the development environment using the provided scripts and `uv`. These scripts automate the installation of dependencies, running tests, and building the project.

## Prerequisites

- **Python**: Version 3.11 or higher.
- **uv**: A fast Python package installer and resolver.
- **Node.js**: Recent version (e.g., v20+).
- **pnpm**: Fast, disk space efficient package manager.

## Initial Setup

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/reecelikesramen/pywire.git
    cd pywire
    ```

2.  **Install everything**:
    The `install` script handles Python `uv sync` (with the workspace configuration) and all `pnpm install` steps for both the client and documentation.
    ```bash
    ./scripts/install
    ```

## Development Scripts

The project uses a set of scripts in the `scripts/` directory to manage common tasks:

| Script | Description |
| --- | --- |
| `./scripts/install` | Installs all Python and pnpm dependencies. |
| `./scripts/test` | Runs Python tests (with coverage) and client tests. |
| `./scripts/coverage` | Displays the coverage report for the `pywire` package. |
| `./scripts/check` | Runs linting (`ruff`) and type checking (`mypy`) via `uv run`. |
| `./scripts/lint` | Runs `ruff` with **auto-fixes** and formatting. |
| `./scripts/docs` | Starts the Astro Starlight development server. |
| `./scripts/build` | Builds the documentation and the client-side bundle. |

## Running Demos

After running `./scripts/install`, you can run the demo applications using `uv run`:

### Demo App
```bash
uv run python demo-app/src/main.py
```

### Demo Routing
```bash
uv run python demo-routing/src/main.py
```

## Troubleshooting

- **ruff/mypy not found**: Ensure you ran `./scripts/install` with `uv` available. The root `pyproject.toml` is configured as a workspace, so `uv sync --all-extras` (called by the install script) installs these tools into the local `.venv`.
- **Lockfile mismatch**: If `uv sync --frozen` fails, run `uv sync --all-extras` once to update the `uv.lock` file.
