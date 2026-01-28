# 🔀 Project Moved: PyWire

The PyWire project has transitioned from this monorepo to a **Polyrepo architecture** under its own GitHub organization. 

Development now takes place at:
### 👉 [github.com/pywire](https://github.com/pywire)

---

## Where did the code go?

To improve modularity and development speed, the components have been split into the following repositories:

*   **[pywire/pywire-workspace](https://github.com/pywire/pywire)**: The aggregator workspace.
*   **[pywire/pywire](https://github.com/pywire/pywire)**: The core framework, compiler, JS client, and documentation.
*   **[pywire/pywire-language-server](https://github.com/pywire/pywire-language-server)**: Official LSP for `.wire` file support.
*   **[pywire/vscode-pywire](https://github.com/pywire/vscode-pywire)**: VS Code extension.
*   **[pywire/pywire.dev](https://github.com/pywire/pywire.dev)**: Main website source.
*   **[pywire/tree-sitter-pywire](https://github.com/pywire/tree-sitter-pywire)**: Tree-sitter grammar.
*   **[pywire/examples](https://github.com/pywire/examples)**: Demo applications.

## Local Development

If you wish to mirror the original monorepo experience locally (working on all components simultaneously), we now use an **aggregator workspace** repo:

**[pywire/pywire-workspace](https://github.com/pywire/pywire-workspace)**

This repository uses **Git Submodules** and **UV Workspaces** to stitch all the individual repos back together into a single, unified development environment.

### Quick Start (New Setup)
```bash
git clone --recursive [https://github.com/pywire/pywire-workspace.git](https://github.com/pywire/pywire-workspace.git)
cd pywire-workspace
./scripts/install
```
