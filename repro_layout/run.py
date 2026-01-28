import sys
import os
import asyncio
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "pywire" / "src"))

from pywire.runtime.loader import PageLoader
from pywire.runtime.page import BasePage
from unittest.mock import MagicMock

async def main():
    loader = PageLoader()
    base_dir = Path(__file__).parent.resolve()
    
    print(f"Loading page from {base_dir}")
    os.chdir(base_dir) # Loader often relies on CWD for relative paths in simple setups
    
    try:
        PageClass = loader.load(base_dir / "page.pywire")
        print(f"Loaded PageClass: {PageClass.__name__}")
        
        # Mock request/app
        request = MagicMock()
        request.app.state.webtransport_cert_hash = None
        request.app.state.enable_pjax = False
        
        page = PageClass(request, {}, {}, {}, None)
        html = await page._render_template()
        
        print("\n=== Rendered HTML ===")
        print(html)
        print("=====================")
        
        if "Page Content" not in html:
            print("FAILURE: 'Page Content' not found in output!")
        else:
            print("SUCCESS: 'Page Content' found.")
            
        if "Custom Header" not in html:
             print("FAILURE: 'Custom Header' not found!")
             
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
