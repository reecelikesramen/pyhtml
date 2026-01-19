from lxml import html

frag1 = "<div>One</div>"
frag2 = "<div>One</div><div>Two</div>"
frag3 = "Text only"

def test(content):
    print(f"\nTesting: {content[:20]}...")
    try:
        res = html.fromstring(content)
        print(f"Result tag: {res.tag}")
    except Exception as e:
        print(f"Error: {e}")

test(frag1)
test(frag2)
test(frag3)
