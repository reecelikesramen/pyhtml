from lxml import html

content = """
<button @click='''
    print("hello")
    x = 1
'''>Click me</button>
"""

try:
    fragments = html.fragments_fromstring(content)
    for frag in fragments:
        if not isinstance(frag, str):
            print(f"Tag: {frag.tag}")
            for name, value in frag.attrib.items():
                print(f"Attr: {name} = {repr(value)}")
except Exception as e:
    print(f"Error: {e}")

content_double = """
<button @click=\"\"\"
    print("double")
    y = 2
\"\"\">Click me</button>
"""

try:
    fragments = html.fragments_fromstring(content_double)
    for frag in fragments:
        if not isinstance(frag, str):
            print(f"Tag: {frag.tag}")
            for name, value in frag.attrib.items():
                print(f"Attr: {name} = {repr(value)}")
except Exception as e:
    print(f"Error: {e}")
