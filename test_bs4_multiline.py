try:
    from bs4 import BeautifulSoup
    
    content = """
    <button @click=\"\"\"
        print("double")
        y = 2
    \"\"\">Click me</button>
    """
    
    soup = BeautifulSoup(content, "html.parser")
    btn = soup.find("button")
    if btn:
        print(f"Tag: {btn.name}")
        for name, value in btn.attrs.items():
            print(f"Attr: {name} = {repr(value)}")
    else:
        print("Button not found")

except ImportError:
    print("BeautifulSoup4 not installed")
except Exception as e:
    print(f"Error: {e}")
