
import pytest
import os
import tempfile
import asyncio
from pathlib import Path
from pyhtml.runtime.loader import PageLoader
from pyhtml.runtime.page import BasePage

@pytest.fixture
def loader():
    return PageLoader()

def test_variable_binding(loader):
    """Test :attr="var" binding."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        page_code = """
<div :id="my_id" :class="my_class"></div>
---
my_id = "dynamic-id"
my_class = "btn"
"""
        (tmp_path / "page.pyhtml").write_text(page_code)
        
        orig_cwd = os.getcwd()
        os.chdir(tmpdir)
        try:
            PageClass = loader.load(tmp_path / "page.pyhtml")
            page = PageClass(None, {}, {}, {}, None)
            html = asyncio.run(page._render_template())
            
            assert 'id="dynamic-id"' in html
            assert 'class="btn"' in html
        finally:
            os.chdir(orig_cwd)

def test_method_binding_paramless(loader):
    """Test :attr="method" auto-call binding."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        page_code = """
<div :title="get_title"></div>
---
def get_title():
    return "My Title"
"""
        (tmp_path / "page.pyhtml").write_text(page_code)
        
        orig_cwd = os.getcwd()
        os.chdir(tmpdir)
        try:
            PageClass = loader.load(tmp_path / "page.pyhtml")
            page = PageClass(None, {}, {}, {}, None)
            html = asyncio.run(page._render_template())
            
            assert 'title="My Title"' in html
        finally:
            os.chdir(orig_cwd)

def test_expression_binding(loader):
    """Test :attr="expr" binding."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        page_code = """
<div :class="'error' if is_error else 'success'"></div>
---
is_error = True
"""
        (tmp_path / "page.pyhtml").write_text(page_code)
        
        orig_cwd = os.getcwd()
        os.chdir(tmpdir)
        try:
            PageClass = loader.load(tmp_path / "page.pyhtml")
            page = PageClass(None, {}, {}, {}, None)
            html = asyncio.run(page._render_template())
            
            assert 'class="error"' in html
        finally:
            os.chdir(orig_cwd)

def test_boolean_attributes(loader):
    """Test boolean attribute behavior."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        page_code = """
<input type="checkbox" :checked="is_checked" :disabled="is_disabled" :readonly="is_readonly">
---
is_checked = True
is_disabled = False
is_readonly = None
"""
        (tmp_path / "page.pyhtml").write_text(page_code)
        
        orig_cwd = os.getcwd()
        os.chdir(tmpdir)
        try:
            PageClass = loader.load(tmp_path / "page.pyhtml")
            page = PageClass(None, {}, {}, {}, None)
            html = asyncio.run(page._render_template())
            
            # checked="True" -> checked=""
            assert 'checked=""' in html
            # disabled="False" -> omitted
            assert 'disabled' not in html
            # readonly="None" -> omitted
            assert 'readonly' not in html
        finally:
            os.chdir(orig_cwd)

def test_async_binding(loader):
    """Test :attr="await async_call()" binding."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        page_code = """
<div :data-val="await get_data()"></div>
---
async def get_data():
    return "async-data"
"""
        (tmp_path / "page.pyhtml").write_text(page_code)
        
        orig_cwd = os.getcwd()
        os.chdir(tmpdir)
        try:
            PageClass = loader.load(tmp_path / "page.pyhtml")
            page = PageClass(None, {}, {}, {}, None)
            html = asyncio.run(page._render_template())
            
            assert 'data-val="async-data"' in html
        finally:
            os.chdir(orig_cwd)


def test_aria_boolean_attributes(loader):
    """Test ARIA boolean attributes (true/false strings)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        page_code = """
<div :aria-busy="is_loading" :aria-expanded="is_expanded"></div>
---
is_loading = True
is_expanded = False
"""
        (tmp_path / "page.pyhtml").write_text(page_code)
        
        orig_cwd = os.getcwd()
        os.chdir(tmpdir)
        try:
            PageClass = loader.load(tmp_path / "page.pyhtml")
            page = PageClass(None, {}, {}, {}, None)
            html = asyncio.run(page._render_template())
            
            # aria-busy="true"
            assert 'aria-busy="true"' in html
            # aria-expanded="false"
            assert 'aria-expanded="false"' in html
        finally:
            os.chdir(orig_cwd)
