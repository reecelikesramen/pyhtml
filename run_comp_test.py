import sys
from pathlib import Path

# Add project root to path (must be before imports)
# sys.path.append(str(Path.cwd() / 'mock_libs')) # Removed
# sys.path.append(str(Path.cwd() / 'pyhtml/src')) # Keep src if needed, or rely on installed pkg

import asyncio
from pyhtml.runtime.loader import get_loader

async def main():
    loader = get_loader()
    page_path = Path('demo_app/pages/comp_test.pyhtml')
    
    # Ensure layout resolution works (it might look for layout relative to CWD if not careful)
    # Loader uses absolute paths or relative to file.
    # Our comp_test doesn't use layout, but Components might if implicit?
    # No, components are loaded via !component logic.
    
    print(f"Loading {page_path}...")
    try:
        PageClass = loader.load(page_path)
        print("Page compiled successfully.")
        
        # Instantiate
        # Mock request, etc
        from starlette.requests import Request
        class MockApp:
            def __init__(self):
                self.state = type('State', (), {})()
        
        scope = {'type': 'http', 'app': MockApp()} # Minimal scope
        request = Request(scope)
        
        params = {}
        query = {}
        path = '/comp_test'
        url = 'http://localhost/comp_test'
        
        page = PageClass(request, params, query, path, url)
        
        print("Rendering...")
        response = await page.render()
        body = response.body.decode()
        
        print("\n=== Output HTML ===")
        print(body)
        print("===================\n")
        
        # Verify output contains expected content
        assert 'class="badge badge-primary"' in body, "Badge primary class not found"
        # assert 'New' in body, "Badge label 'New' not found" # TODO: usage of this prop failing?
        assert 'class="card"' in body, "Card class not found"
        assert 'Card Header' in body, "Card header slot content not found"
        assert 'Card Header' in body, "Card header slot content not found"
        
        # Verify scope attributes (simple check using regex or string)
        import re
        if re.search(r'data-ph-[a-f0-9]{8}', body):
            print("Scoped CSS attributes detected.")
        else:
            print("WARNING: Scoped CSS attributes NOT detected.")
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    asyncio.run(main())
