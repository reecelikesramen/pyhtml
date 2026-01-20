"""Main entry point for demo app."""
from pyhtml import PyHTML

# Create app instance
app = PyHTML(
    path_based_routing=False,
    debug=True
)
