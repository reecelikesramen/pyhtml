import asyncio
import os
import sys

# Ensure project root is in path
sys.path.insert(0, os.getcwd())

from pyhtml.runtime.dev_server import run_dev_server

if __name__ == "__main__":
    # Run the dev server targeting the demo-components app
    # host="0.0.0.0" allows access from outside container/vm if needed, but localhost is fine for local.
    # We use localhost to match the cert generation logic which targets localhost.
    asyncio.run(run_dev_server(
        app_str="demo_components.main:app",
        host="127.0.0.1",
        port=8000
    ))
