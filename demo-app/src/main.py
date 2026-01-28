"""Main entry point for demo app."""
from pywire import PyWire

# Create app instance
app = PyWire(
    path_based_routing=False,
    static_dir="static",
    debug=True
)
