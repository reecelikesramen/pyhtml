"""Main entry point for demo app."""
from pyhtml import PyHTML

# Create app instance
app = PyHTML(
    path_based_routing=False,
    static_dir="src/static",
    debug=True
)
