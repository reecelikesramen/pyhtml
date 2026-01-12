"""Directive parsers."""
from pyhtml.compiler.directives.base import DirectiveParser
from pyhtml.compiler.directives.path import PathDirectiveParser
from pyhtml.compiler.directives.no_spa import NoSpaDirectiveParser

__all__ = ['DirectiveParser', 'PathDirectiveParser', 'NoSpaDirectiveParser']
