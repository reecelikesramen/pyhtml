from unittest.mock import MagicMock

import pytest
from pyhtml.compiler.exceptions import PyHTMLSyntaxError
from pyhtml.runtime.compile_error_page import CompileErrorPage
from starlette.requests import Request


@pytest.fixture
def mock_request():
    request = MagicMock(spec=Request)
    request.scope = {"type": "http", "server": ("localhost", 8000), "path": "/"}
    return request


@pytest.fixture
def temp_pyhtml_file(tmp_path):
    file_path = tmp_path / "test.pyhtml"
    content = "\n".join([f"line {i}" for i in range(1, 20)])
    file_path.write_text(content)
    return str(file_path)


@pytest.mark.asyncio
async def test_compile_error_page_syntax_error(mock_request, temp_pyhtml_file):
    error = PyHTMLSyntaxError("Invalid syntax", file_path=temp_pyhtml_file, line=10)
    page = CompileErrorPage(mock_request, error)

    response = await page.render()
    content = response.body.decode()

    assert "PyHTML Syntax Error" in content
    assert "Invalid syntax" in content
    assert "line 10" in content
    assert "line-num'>10</span>" in content
    assert "line-current" in content


@pytest.mark.asyncio
async def test_compile_error_page_generic_exception(mock_request, temp_pyhtml_file):
    try:
        # Create an exception with a traceback
        raise ValueError("Something went wrong")
    except Exception as e:
        error = e

    page = CompileErrorPage(mock_request, error, file_path=temp_pyhtml_file)

    response = await page.render()
    content = response.body.decode()

    assert "Compilation Error" in content
    assert "ValueError: Something went wrong" in content
    assert "Full Traceback" in content
    assert "ValueError" in content


@pytest.mark.asyncio
async def test_compile_error_page_traceback_inference(mock_request, tmp_path):
    # Create a dummy file and raise an error that "looks" like it came from there
    file_path = tmp_path / "app_logic.pyhtml"
    file_path.write_text("dummy content")

    def raise_err():
        raise RuntimeError("Fail")

    try:
        raise_err()
    except Exception as e:
        error = e

    page = CompileErrorPage(mock_request, error)

    response = await page.render()
    content = response.body.decode()

    assert "RuntimeError: Fail" in content
    assert "Full Traceback" in content


@pytest.mark.asyncio
async def test_compile_error_page_missing_file(mock_request):
    error = PyHTMLSyntaxError("Bad", file_path="/non/existent/file.pyhtml", line=1)
    page = CompileErrorPage(mock_request, error)

    response = await page.render()
    content = response.body.decode()

    assert "Bad" in content
    # Should not crash even if file missing
    assert 'class="code-context"' not in content  # Use class=" to distinguish from CSS
