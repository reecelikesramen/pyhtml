"""PyHTML configuration for demo app."""
from pathlib import Path

# Pages directory
PAGES_DIR = Path(__file__).parent / 'pages'

# Components directory  
COMPONENTS_DIR = Path(__file__).parent / 'components'

# Development settings
DEBUG = True
HOST = '127.0.0.1'
PORT = 3000
