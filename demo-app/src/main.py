"""Main entry point for demo app."""
import asyncio
from pathlib import Path

import uvicorn

from pyhtml.runtime.app import PyHTMLApp


def main():
    """Run the demo app."""
    # Get the pages directory (src/pages relative to this file)
    pages_dir = Path(__file__).parent / 'pages'
    
    # Create app
    app = PyHTMLApp(pages_dir)
    
    # Bootstrap chatbot DB
    try:
        from pages.chatbot.models import Base, engine
        Base.metadata.create_all(engine)
        print("Chatbot database initialized.")
    except ImportError:
        # If we're not running in an environment where pages is importable, 
        # or it's not the chatbot demo, just skip.
        pass
    except Exception as e:
        print(f"Failed to bootstrap chatbot DB: {e}")
    
    # Run with uvicorn
    config = uvicorn.Config(
        app.app,
        host='127.0.0.1',
        port=3000,
        reload=True,
        reload_dirs=[str(pages_dir)],
        reload_includes=["*.pyhtml", "*.py"],
    )
    
    server = uvicorn.Server(config)
    asyncio.run(server.serve())


if __name__ == '__main__':
    main()
