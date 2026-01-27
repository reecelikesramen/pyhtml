# PyHTML Demo App

This is a demo application showcasing PyHTML framework features.

## Setup

1. Install dependencies:
```bash
pip install -e ../pyhtml
pip install -e .
```

2. Run the app:
```bash
# Option 1: Using the CLI
cd ..
pyhtml dev --pages-dir demo-app/src/pages

# Option 2: Direct Python
python -m src.main
```

## Features Demonstrated

- **Variable Interpolation**: `{name}` and `{count}` in the template
- **Event Handlers**: `@click={increment_count}` on the button
- **Lifecycle Hooks**: `__on_load()` for initialization
- **Routing**: `!path { 'home': '/' }` directive

## Project Structure

```
demo-app/
├── src/
│   ├── pages/
│   │   └── index.pyhtml    # Main page
│   ├── components/          # Reusable components (future)
│   ├── main.py              # App entry point
│   └── pyhtml.config.py    # Configuration
└── pyproject.toml           # Dependencies
```
