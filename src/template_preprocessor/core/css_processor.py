#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Django template preprocessor.
Author: Jonathan Slenders, City Live
"""


"""
CSS parser for the template preprocessor.
-----------------------------------------------

Similar to the javascript preprocessor. This
will precompile the CSS in the parse tree.
"""

from django.conf import settings

from template_preprocessor.core.django_processor import DjangoContent, DjangoContainer
from template_preprocessor.core.lexer import State, StartToken, Push, Record, Shift, StopToken, Pop, CompileException, Token, Error
from template_preprocessor.core.lexer_engine import tokenize
from template_preprocessor.core.html_processor import HtmlNode, HtmlContent
import string
import os

__CSS_STATES = {
    'root' : State(
            # Operators for which it's allowed to remove the surrounding whitespace
            # Note that the dot (.) and hash (#) operators are not among these. Removing whitespace before them
            # can cause their meaning to change.
            State.Transition(r'\s*[{}():;,]\s*', (StartToken('css-operator'), Record(), Shift(), StopToken(), )),

            # Strings
            State.Transition(r'"', (Push('double-quoted-string'), StartToken('css-double-quoted-string-open'), Record(), Shift(), )),
            State.Transition(r"'", (Push('single-quoted-string'), StartToken('css-single-quoted-string-open'), Record(), Shift(), )),

            # Comments
            State.Transition(r'/\*', (Push('multiline-comment'), Shift(), )),
            State.Transition(r'//', (Push('singleline-comment'), Shift(), )),

            # Skip over comment signs. (not part of the actual css, and automatically inserted later on before and after
            # the css.)
            State.Transition(r'(<!--|-->)', (Shift(), )),

            # URLs like in url(...)
            State.Transition(r'url\(', (Shift(), StartToken('css-url'), Push('css-url'), )),


            # 'Words' (multiple of these should always be separated by whitespace.)
            State.Transition('([^\s{}();:,"\']|/(!?[/*]))+', (Record(), Shift(), )),

            # Whitespace which can be minified to a single space, but shouldn't be removed completely.
            State.Transition(r'\s+', (StartToken('css-whitespace'), Record(), Shift(), StopToken() )),

            State.Transition(r'.|\s', (Error('Error in parser #1'),)),
            ),
    'double-quoted-string': State(
            State.Transition(r'"', (Record(), Pop(), Shift(), StopToken(), )),
            State.Transition(r'\\.', (Record(), Shift(), )),
            State.Transition(r'[^"\\]+', (Record(), Shift(), )),
            State.Transition(r'.|\s', (Error('Error in parser #2'),)),
            ),
    'single-quoted-string': State(
            State.Transition(r"'", (Record(), Pop(), Shift(), StopToken(), )),
            State.Transition(r'\\.', (Record(), Shift() )),
            State.Transition(r"[^'\\]+", (Record(), Shift(), )),
            State.Transition(r'.|\s', (Error('Error in parser #3'),)),
            ),
    'multiline-comment': State(
            State.Transition(r'\*/', (Shift(), Pop(), )), # End comment
            State.Transition(r'(\*(?!/)|[^\*])+', (Shift(), )), # star, not followed by slash, or non star characters
            State.Transition(r'.|\s', (Error('Error in parser #4'),)),
            ),

    'css-url': State(
            # Strings inside urls (don't record the quotes, just place the content into the 'css-url' node)
            State.Transition(r'"', (Push('css-url-double-quoted'), Shift(), )),
            State.Transition(r"'", (Push('css-url-single-quoted'), Shift(), )),
            State.Transition("[^'\"\\)]+", (Record(), Shift())),

            State.Transition(r'\)', (Shift(), Pop(), StopToken(), )), # End url(...)
            State.Transition(r'.|\s', (Error('Error in parser #5'),)),
            ),
    'css-url-double-quoted': State(
            State.Transition(r'"', (Shift(), Pop(), )),
            State.Transition(r'\\.', (Record(), Shift() )),
            State.Transition(r'[^"\\]', (Record(), Shift())),
            ),
    'css-url-single-quoted': State(
            State.Transition(r"'", (Shift(), Pop(), )),
            State.Transition(r'\\.', (Record(), Shift() )),
            State.Transition(r"[^'\\]", (Record(), Shift())),
            ),

            # Single line comment (however, not allowed by the CSS specs.)
    'singleline-comment': State(
            State.Transition(r'\n', (Shift(), Pop(), )), # End of line is end of comment
            State.Transition(r'[^\n]+', (Shift(), )),
            State.Transition(r'.|\s', (Error('Error in parser #6'),)),
            ),
}


class CssNode(HtmlContent):
    pass

class CssOperator(HtmlContent):
    pass

class CssDoubleQuotedString(HtmlContent):
    pass

class CssWhitespace(HtmlContent):
    pass

class CssUrl(HtmlContent):
    def init_extension(self):
        self.url = self._unescape(self.output_as_string(True))

    def _unescape(self, url):
        import re
        return re.sub(r'\\(.)', r'\1', url)

    def _escape(self, url):
        import re
        return re.sub(r"'", r'\\\1', url)

    def output(self, handler):
        handler("url('")
        handler(self._escape(self.url))
        handler("')")


__CSS_EXTENSION_MAPPINGS = {
        'css-operator': CssOperator,
        'css-double-quoted-string': CssDoubleQuotedString,
        'css-whitespace': CssWhitespace,
        'css-url': CssUrl,
}


def _add_css_parser_extensions(css_node):
    """
    Patch nodes in the parse tree, to get the CSS parser functionality.
    """
    for node in css_node.children:
        if isinstance(node, Token):
            # Patch the js scope class
            if node.name in __CSS_EXTENSION_MAPPINGS:
                node.__class__ = __CSS_EXTENSION_MAPPINGS[node.name]
                if hasattr(node, 'init_extension'):
                    node.init_extension()

            _add_css_parser_extensions(node)


def _rewrite_urls(css_node, base_url):
    """
    Rewrite url(../img/img.png) to an absolute url, by
    joining it with its own public path.
    """
    def is_absolute_url(url):
        # An URL is absolute when it contains a protocol definition
        # like http:// or when it starts with a slash.
        return '://' in url or url[0] == '/'

    directory = os.path.dirname(base_url)

    for url_node in css_node.child_nodes_of_class([ CssUrl ]):
        if not is_absolute_url(url_node.url):
            url_node.url = os.path.normpath(os.path.join(directory, url_node.url))

    # Replace urls starting with /static and /media with the real static and
    # media urls. We cannot use settings.MEDIA_URL/STATIC_URL in external css
    # files, and therefore we simply write /media or /static.
    from template_preprocessor.core.utils import real_url
    for url_node in css_node.child_nodes_of_class([ CssUrl ]):
        url_node.url = real_url(url_node.url)


def _compress_css_whitespace(css_node):
    """
    Remove all whitepace in the css code where possible.
    """
    for c in css_node.children:
        if isinstance(c, CssOperator):
            # Around operators, we can delete all whitespace.
            c.children = [ c.output_as_string().strip()  ]

        if isinstance(c, CssWhitespace):
            # Whitespace tokens to be kept. (but minified into one character.)
            c.children = [ u' ' ]

        if isinstance(c, Token):
            _compress_css_whitespace(c)


def compile_css(css_node, context):
    """
    Compile the css nodes to more compact code.
    - Remove comments
    - Remove whitespace where possible.
    """
    #_remove_multiline_js_comments(js_node)
    tokenize(css_node, __CSS_STATES, [HtmlNode], [DjangoContainer])
    _add_css_parser_extensions(css_node)

    # Remove meaningless whitespace in javascript code.
    _compress_css_whitespace(css_node)


def compile_css_string(css_string, context, path='', url=None):
    """
    Compile CSS code
    """
    # First, create a tree to begin with
    tree = Token(name='root', line=1, column=1, path=path)
    tree.children = [ css_string ]

    # Tokenize
    tokenize(tree, __CSS_STATES, [Token] )
    _add_css_parser_extensions(tree)

    # Rewrite url() in external css files
    if url:
        _rewrite_urls(tree, url)

    # Compile
    _compress_css_whitespace(tree)

    # Output
    return u''.join([o for o in tree.output_as_string() ])
