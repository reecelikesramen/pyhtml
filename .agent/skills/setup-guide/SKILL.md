---
name: Setup Guide
description: Instructions for setting up the environment for a fresh clone, installing dependencies, and running tests/demos.
---

# Setup Guide for PyHTML

This guide covers how to set up the development environment for a fresh clone of the PyHTML repository. It includes instructions for installing dependencies for all subprojects, running tests, compiling the client, and running demo applications.

## Prerequisites

- **Python**: Version 3.11 or higher.
- **Node.js**: Recent version (e.g., 18+ or 20+).
- **npm**: Included with Node.js.

## Initial Setup

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/reecelikesramen/pyhtml.git
    cd pyhtml
    ```

2.  **Create and activate a virtual environment**:
    ```bash
    python3.11 -m venv .venv
    source .venv/bin/activate  # On Windows: .venv\Scripts\activate
    ```

## Installing Dependencies

The repository consists of several components. You should install dependencies for the components you intend to work on.

### Core Framework (`pyhtml`)

To install the core library in editable mode with development dependencies:

```bash
pip install -e "pyhtml[dev]"
```

### Language Server (`lsp`)

To install the LSP server in editable mode:

```bash
pip install -e lsp
```

### Demo Applications

Dependencies for demo apps are managed via their own `pyproject.toml` files.

-   **Demo App**:
    ```bash
    pip install -e demo-app
    ```

-   **Demo Routing**:
    ```bash
    pip install -e demo-routing
    ```

### Client-Side Code (`pyhtml/src/pyhtml/client`)

The core client logic (TypeScript) requires Node.js dependencies.

```bash
cd pyhtml/src/pyhtml/client
npm install
```

### VS Code Extension (`vscode-pyhtml`)

If you are working on the VS Code extension:

```bash
cd vscode-pyhtml
npm install
```

## Running Tests

### Python Tests (Framework & LSP)

From the root directory, you can run all Python tests using `pytest`. This includes tests for both the core framework and the LSP.

```bash
pytest
```

Required dependencies: `pyhtml[dev]` and `lsp` (for LSP tests).

### Client Tests

To run the TypeScript client tests:

```bash
cd pyhtml/src/pyhtml/client
npm test
```

## Compiling the Client

The PyHTML client needs to be compiled into a simplified bundle.

```bash
cd pyhtml/src/pyhtml/client
npm run build
```

Use `npm run watch` for development to rebuild on changes.

## Compiling the VS Code Extension

```bash
cd vscode-pyhtml
npm run compile
```

## Running Demo Applications

After installing their dependencies (and the core framework), you can run the demo apps directly with Python.

### Demo App

```bash
# From root directory
python demo-app/src/main.py
```

### Demo Routing

```bash
# From root directory
python demo-routing/src/main.py
```

## Troubleshooting

-   **Tree-sitter issues**: If you encounter errors related to `tree-sitter` in the VS Code extension or LSP, ensure you have the correct build tools installed for your platform (e.g., C++ compiler).
-   **Missing dependencies**: If `pip install` fails, check that you are in the virtual environment and your pip is up to date (`pip install --upgrade pip`).
