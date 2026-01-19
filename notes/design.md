# Feature: forms

## Basic with dictionary
```
<form @submit="handle_form_submission">
    <input name="username">
    <input name="password">
</form>

---

def handle_form_submission(data):
    User.create(data["username"], data["password"])

```

## Basic with Pydantic model
```
<form @submit="handle_form_pydantic" $model="Model">
    <input name="A" $field="a">
    <input name="B" $field="b">
    <input name="C" $field="c">
</form>
---
from pydantic import BaseModel

class Model(BaseModel):
    a: int
    b: float
    c: str

async def handle_form_pydantic(model):
    # do stuff with model, it's already bound
```

## Forms with automatic server validation
https://developer.mozilla.org/en-US/docs/Learn_web_development/Extensions/Forms/Form_validation
```
<form @submit="handle_validated_form">
    <input name="username" pattern="[A-Za-z0-9]{3,15}">
    <input name="password" minlength="8">
</form>

---

def handle_validated_form(data):
    # data["username"] is guaranteed to match pattern, client side AND server-side (we inject validation based on the HTML client-side validation)
    # data["password"] is guaranteed to be >= 8 chars
```

