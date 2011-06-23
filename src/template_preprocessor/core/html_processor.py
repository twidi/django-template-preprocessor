#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Django template preprocessor.
Author: Jonathan Slenders, City Live
"""

"""
HTML parser for the template preprocessor.
-----------------------------------------------

Parses HTML in de parse tree. (between django template tags.)
"""

from template_preprocessor.core.django_processor import *
from template_preprocessor.core.lexer import State, StartToken, Push, Record, Shift, StopToken, Pop, CompileException, Token, Error
from template_preprocessor.core.lexer_engine import tokenize, nest_block_level_elements
from template_preprocessor.core.utils import check_external_file_existance, is_remote_url

from copy import deepcopy
from django.conf import settings

import codecs
import os
import string


# HTML 4 tags
__HTML4_BLOCK_LEVEL_ELEMENTS = ('html', 'head', 'body', 'meta', 'script', 'noscript', 'p', 'div', 'ul', 'ol', 'dl', 'dt', 'dd', 'li', 'table', 'td', 'tr', 'th', 'thead', 'tfoot', 'tbody', 'br', 'link', 'title', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'form', 'object', 'base', 'iframe', 'fieldset', 'code', 'blockquote', 'legend', 'pre', 'embed')
__HTML4_INLINE_LEVEL_ELEMENTS = ('address', 'span', 'a', 'b', 'i', 'em', 'del', 'ins', 'strong', 'select', 'label', 'q', 'sub', 'sup', 'small', 'sub', 'sup', 'option', 'abbr', 'img', 'input', 'hr', 'param', 'button', 'caption', 'style', 'textarea', 'colgroup', 'col', 'samp', 'kbd', 'map', 'optgroup', 'strike', 'var', 'wbr', 'dfn')

# HTML 5 tags
__HTML5_BLOCK_LEVEL_ELEMENTS = ( 'article', 'aside', 'canvas', 'figcaption', 'figure', 'footer', 'header', 'hgroup', 'output', 'progress', 'section', 'video', )
__HTML5_INLINE_LEVEL_ELEMENTS = ('audio', 'details', 'command', 'datalist', 'mark', 'meter', 'nav', 'source', 'summary', 'time', 'samp', )

# All HTML tags
__HTML_BLOCK_LEVEL_ELEMENTS = __HTML4_BLOCK_LEVEL_ELEMENTS + __HTML5_BLOCK_LEVEL_ELEMENTS
__HTML_INLINE_LEVEL_ELEMENTS = __HTML4_INLINE_LEVEL_ELEMENTS + __HTML5_INLINE_LEVEL_ELEMENTS


# Following tags are also listed as block elements, but this list can only contain inline-elements.
__HTML_INLINE_BLOCK_ELEMENTS = ('h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'img', 'object', 'button')


        # HTML tags consisting of separate open and close tag.
__ALL_HTML_TAGS = __HTML_BLOCK_LEVEL_ELEMENTS + __HTML_INLINE_LEVEL_ELEMENTS

__DEPRECATED_HTML_TAGS = ('i', 'b', 'u', 'tt', 'strike', )

__HTML_ATTRIBUTES = {
    # Valid for every HTML tag
    '_': ('accesskey', 'id', 'class', 'contenteditable', 'contextmenu', 'dir', 'draggable', 'dropzone', 'hidden', 'spellcheck', 'style', 'tabindex', 'lang', 'xmlns', 'title', 'xml:lang'),

    # Attributes for specific HTML tags

    'a': ('href', 'hreflang', 'media', 'type', 'target', 'rel', 'name', 'share_url'), # share_url is not valid, but used in the facebook share snipped.
    'audio': ('autoplay', 'controls', 'loop', 'preload', 'src'),
    'canvas': ('height', 'width'),
    'font': ('face', 'size', ),
    'form': ('action', 'method', 'enctype', 'name', ),
    'html': ('xmlns', 'lang', 'dir', ),
    'body': ('onLoad', ),
    'img': ('src', 'alt', 'height', 'width', ),
    'input': ('type', 'name', 'value', 'maxlength', 'checked', 'disabled', 'src', 'size', 'readonly' ),
    'select': ('name', 'value', 'size', ),
    'textarea': ('name', 'rows', 'cols', 'readonly', ),
    'link': ('type', 'rel', 'href', 'media', 'charset', ),
    'meta': ('content', 'http-equiv', 'name', ),
    'script': ('type', 'src', 'language', 'charset', ),
    'style': ('type', 'media', ),
    'td': ('colspan', 'rowspan', ),
    'th': ('colspan', 'rowspan', 'scope', ),
    'button': ('value', 'type', 'name', ),
    'label': ('for', ),
    'option': ('value', 'selected', ),
    'base': ('href', ),
    'object': ('data', 'type', 'width', 'height', 'quality', ),
    'iframe': ('src', 'srcdoc', 'name', 'height', 'width', 'marginwidth', 'marginheight', 'scrolling', 'sandbox', 'seamless', 'frameborder', 'allowTransparency',),
    'param': ('name', 'value', ),
    'table': ('cellpadding', 'cellspacing', 'summary', 'width', ),
    'p': ('align', ), # Deprecated
    'embed': ('src', 'allowscriptaccess', 'height', 'width', 'allowfullscreen', 'type', ),
    'video': ('audio', 'autoplay', 'controls', 'height', 'loop', 'poster', 'preload', 'src', 'width'),
}

# TODO: check whether forms have {% csrf_token %}
# TODO: check whether all attributes are valid.

def xml_escape(s):
    # XML escape
    s = unicode(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')#.replace("'", '&#39;')

    # Escape braces, to make sure Django tags will not be rendered in here.
    s = unicode(s).replace('}', '&#x7d;').replace('{', '&#x7b;')

    return s



__HTML_STATES = {
    'root' : State(
            # conditional comments
            State.Transition(r'<!(--)?\[if', (StartToken('html-start-conditional-comment'), Record(), Shift(), Push('conditional-comment'), )),
            State.Transition(r'<!(--)?\[endif\](--)?>', (StartToken('html-end-conditional-comment'), Record(), Shift(), StopToken(), )),
            State.Transition(r'<!\[CDATA\[', (StartToken('html-cdata'), Shift(), Push('cdata'), )),

            # XML doctype
            State.Transition(r'<!DOCTYPE', (StartToken('html-doctype'), Record(), Shift(), Push('doctype'), )),

            # HTML comments
            State.Transition(r'<!--', (StartToken('html-comment'), Shift(), Push('comment'), )),

            # HTML tags
            State.Transition(r'</(?=\w)', (StartToken('html-end-tag'), Shift(), Push('tag'), )),
            State.Transition(r'<(?=\w)', (StartToken('html-tag'), Shift(), Push('tag'), )),

            State.Transition(r'&', (StartToken('html-entity'), Record(), Shift(), Push('entity'), )),

            # Content
            State.Transition(r'([^<>\s&])+', (StartToken('html-content'), Record(), Shift(), StopToken(), )),

            # Whitespace
            State.Transition(r'\s+', (StartToken('html-whitespace'), Record(), Shift(), StopToken(), )),

            State.Transition(r'.|\s', (Error('Parse error in HTML document'), )),
            ),
    'conditional-comment': State(
            State.Transition(r'[\s\w()!|&]+', (Record(), Shift(), )),
            State.Transition(r'\](--)?>', (Record(), Shift(), Pop(), StopToken(), )),
            State.Transition(r'.|\s', (Error('Parse error in Conditional Comment'), )),
            ),
    'comment': State(
            # End of comment
            State.Transition(r'-->', (Shift(), Pop(), StopToken(), )),

            # Comment content
            State.Transition(r'([^-]|-(?!->))+', (Record(), Shift(), )),

            State.Transition(r'.|\s', (Error('Parse error in HTML comment'), )),
            ),
    'cdata': State(
            # End of CDATA block
            State.Transition(r'\]\]>', (Shift(), Pop(), StopToken() )),

            # CDATA content
            State.Transition(r'([^\]]|\](?!\]>))+', (Record(), Shift(), )),

            State.Transition(r'.|\s', (Error('Parse error in CDATA tag'), )),
            ),
    'doctype': State(
            State.Transition(r'[^>\s]+', (Record(), Shift(), )),
            State.Transition(r'\s+', (Record(' '), Shift(), )),
            State.Transition(r'>', (Record(), StopToken(), Shift(), Pop(), )),

            State.Transition(r'.|\s', (Error('Parse error in doctype tag'), )),
            ),
    'tag': State(
            # At the start of an html tag
            State.Transition('[^\s/>]+', (StartToken('html-tag-name'), Record(), Shift(), StopToken(), Pop(), Push('tag2'), )),

            State.Transition(r'.|\s', (Error('Parse error in HTML tag'), )),
            ),
    'tag2': State( # Inside the html tag
            # HTML tag attribute
            State.Transition(r'[\w:_-]+=', (StartToken('html-tag-attribute'),
                                            StartToken('html-tag-attribute-key'), Record(), Shift(), StopToken(),
                                            StartToken('html-tag-attribute-value'), Push('attribute-value'), )),

            # HTML tag attribute (oldstyle without = sign
            State.Transition(r'[\w:_-]+(?!=)', (StartToken('html-tag-attribute'), StartToken('html-tag-attribute-key'),
                                                    Record(), Shift(), StopToken(), StopToken(), )),

            # End of html tag
            State.Transition(r'\s*/>', (StartToken('html-tag-end-sign'), StopToken(), Shift(), Pop(), StopToken(), )),
            State.Transition(r'\s*>', (Shift(), Pop(), StopToken(), )),

            # Whitespace
            State.Transition(r'\s+', (Shift(), StartToken('html-tag-whitespace'), Record(' '), StopToken(), )),

            State.Transition(r'.|\s', (Error('Parse error in HTML tag'), )),
            ),
    'entity': State(
            State.Transition(r';', (Record(), Shift(), Pop(), StopToken() )),
            State.Transition(r'[#a-zA-Z0-9]+', (Record(), Shift(), )),
            State.Transition(r'.|\s', (Error('Parse error in HTML entity'), )),
            ),
    'attribute-value': State(
            # Strings or word characters
            State.Transition(r"'", (Record(), Shift(), Push('attribute-string'), )),
            State.Transition(r'"', (Record(), Shift(), Push('attribute-string2'), )),
            State.Transition(r'\w+', (Record(), Shift(), )),

            # Anything else? Pop back to the tag
            State.Transition(r'\s|.', (Pop(), StopToken(), StopToken() )),
            ),

    'attribute-string': State( # Double quoted
                    # NOTE: We could also use the regex r'"[^"]*"', but that won't work
                    #       We need a separate state for the strings, because the string itself could
                    #       contain a django tag, and it works this way in lexer.
            State.Transition(r"'", (Record(), Shift(), Pop(), Pop(), StopToken(), StopToken(), )),
            State.Transition(r'&', (StartToken('html-entity'), Record(), Shift(), Push('entity'), )),
            State.Transition(r"[^'&]+", (Record(), Shift(), )),
            ),
    'attribute-string2': State( # Single quoted
            State.Transition(r'"', (Record(), Shift(), Pop(), Pop(), StopToken(), StopToken(), )),
            State.Transition(r'&', (StartToken('html-entity'), Record(), Shift(), Push('entity'), )),
            State.Transition(r'[^"&]+', (Record(), Shift(), )),
            ),
    }


# ==================================[  HTML Parser Extensions ]================================

class HtmlNode(DjangoContent):
    """
    base class
    """
    pass

class HtmlDocType(HtmlNode):
    pass

class HtmlEntity(HtmlNode):
    pass

class HtmlConditionalComment(HtmlNode):
    """
    Contains:
    <!--[if ...]> children <![endif ...]-->
    """
    def process_params(self, params):
        self.__start = u''.join(params)

    def output(self, handler):
        handler(self.__start)
        Token.output(self, handler)
        handler(u'<![endif]-->')


class HtmlContent(HtmlNode):
    pass

class HtmlWhiteSpace(HtmlContent):
    def compress(self):
        self.children = [u' ']

class HtmlComment(HtmlNode):
    def init_extension(self):
        self.__show_comment_signs = True

    def remove_comment_signs(self):
        self.__show_comment_signs = False

    def output(self, handler):
        if self.__show_comment_signs: handler('<!--')
        Token.output(self, handler)
        if self.__show_comment_signs: handler('-->')

class HtmlCDATA(HtmlNode):
    def init_extension(self):
        self.__show_cdata_signs = True

    def remove_cdata_signs(self):
        self.__show_cdata_signs = False

    def output(self, handler):
        if self.__show_cdata_signs: handler('<![CDATA[')
        Token.output(self, handler)
        if self.__show_cdata_signs: handler(']]>')


class HtmlTag(HtmlNode):
    @property
    def html_attributes(self):
        attributes = {}

        for a in self.child_nodes_of_class([ HtmlTagAttribute ]):
            attributes[a.attribute_name] = a.attribute_value

        return attributes

    def get_html_attribute_value_as_string(self, name):
        """
        Return attribute value. *Fuzzy* because it will render possible template tags
        in the string, and strip double quotes.
        """
        attrs = self.html_attributes
        if name in attrs:
            result = attrs[name].output_as_string()
            return result.strip('"\'')
        return None

    def is_inline(self):
        return self.html_tagname in __HTML_INLINE_LEVEL_ELEMENTS

    @property
    def is_closing_html_tag(self):
        """
        True when we have the slash, like in "<img src=...  />"
        """
        for c in self.children:
            if isinstance(c, HtmlTagEndSign):
                return True
        return False

    @property
    def html_tagname(self):
        """
        For <img src="..." />, return 'img'
        """
        for c in self.children:
            if c.name == 'html-tag-name':
                return c.output_as_string()

    def set_html_attribute(self, name, attribute_value):
        """
        Replace attribute and add double quotes.
        """
        # Delete attributes having this name
        for a in self.child_nodes_of_class([ HtmlTagAttribute ]):
            if a.attribute_name == name:
                self.remove_child_nodes([ a ])

        # Set attribute
        self.add_attribute(name, '"%s"' % xml_escape(attribute_value))


    def add_attribute(self, name, attribute_value):
        """
        Add a new attribute to this html tag.
        """
        # First, create a whitespace, to insert before the attribute
        ws = HtmlTagWhitespace()
        ws.children = [ ' ' ]

        # Attribute name
        n= HtmlTagAttributeName()
        n.children = [ name, '=' ]

        # Attribute
        a = HtmlTagAttribute()
        a.children = [n, attribute_value]

        # If we have a slash at the end, insert the attribute before the slash
        if isinstance(self.children[-1], HtmlTagEndSign):
            self.children.insert(-1, ws)
            self.children.insert(-1, a)
        else:
            self.children.append(ws)
            self.children.append(a)

    def output(self, handler):
        handler('<')
        Token.output(self, handler)
        handler('>')

    def remove_whitespace_in_html_tag(self):
        """
        Remove all whitespace that can removed between
        attributes. (To be called after removing attributes.)
        """
        i = -1

        while isinstance(self.children[i], HtmlTagEndSign):
            i -= 1

        while self.children and isinstance(self.children[i], HtmlTagWhitespace):
            self.children.remove(self.children[i])


class HtmlTagName(HtmlNode):
    pass


class HtmlEndTag(HtmlNode):
    @property
    def html_tagname(self):
        for c in self.children:
            if c.name == 'html-tag-name':
                return c.output_as_string()

    @property
    def is_closing_html_tag(self):
        return False

    def output(self, handler):
        handler('</')
        Token.output(self, handler)
        handler('>')

class HtmlTagEndSign(HtmlNode):
    def output(self, handler):
        """
        This is the '/' in <span />
        """
        handler('/')
        # yield ' /' # Do we need a space before the closing slash?

class HtmlTagAttribute(HtmlNode):
    @property
    def attribute_name(self):
        """
        Return attribute name
        (Result is a string)
        """
        key = list(self.child_nodes_of_class([ HtmlTagAttributeName ]))[0]
        key = key.output_as_string()
        return key.rstrip('=')

    @property
    def attribute_value(self):
        """
        Return attribute value, or None if none was given (value can be optional (HTML5))
        (result is nodes or None)
        """
        val = list(self.child_nodes_of_class([ HtmlTagAttributeValue ]))
        return val[0] if val else None


class HtmlTagPair(HtmlNode):
    """
    Container for the opening HTML tag, the matching closing HTML
    and all the content. (e.g. <p> + ... + </p>)
    This is overriden for every possible HTML tag.
    """
    pass


class HtmlTagWhitespace(HtmlNode):
    pass

class HtmlTagAttributeName(HtmlNode):
    pass


class HtmlTagAttributeValue(HtmlNode):
    def init_extension(self):
        self.__double_quotes = False

    def output(self, handler):
        if self.__double_quotes:
            handler('"')

        Token.output(self, handler)

        if self.__double_quotes:
            handler('"')


class HtmlScriptNode(HtmlNode):
    """
    <script type="text/javascript" src="..."> ... </script>
    """
    html_tagname = 'script'
    def process_params(self, params):
        # Create dictionary of key/value pairs for this script node
        self.__attrs = { }
        for p in params:
            if isinstance(p, HtmlTagAttribute):
                key = list(p.child_nodes_of_class([ HtmlTagAttributeName ]))[0]
                val = list(p.child_nodes_of_class([ HtmlTagAttributeValue ]))[0]

                key = key.output_as_string()
                val = val.output_as_string()

                self.__attrs[key] = val

        self.is_external = ('src=' in self.__attrs)

    def _get_script_source(self):
        """
        Return a string containing the value of the 'src' property without quotes.
        ** Note that this property is a little *fuzzy*!
           It can return a django tag like '{{ varname }}', but as a string.
        """
        if self.is_external:
            return self.__attrs['src='].strip('"\'')

    def _set_script_source(self, value):
        self.__attrs['src='] = '"%s"' % xml_escape(value)

    script_source = property(_get_script_source, _set_script_source)

    def output(self, handler):
        handler('<script ')
        handler(u' '.join([ u'%s%s' % (a, self.__attrs[a]) for a in self.__attrs.keys() ]))
        handler('>')

        if not self.is_external:
            handler('//<![CDATA[\n')

        Token.output(self, handler)

        if not self.is_external:
            handler(u'//]]>\n')

        handler(u'</script>')


class HtmlStyleNode(HtmlNode):
    """
    <style type="text/css"> ... </style>
    """
    html_tagname = 'style'

    def process_params(self, params):
        self.is_external = False # Always False

    def output(self, handler):
        handler(u'<style type="text/css"><!--')
        Token.output(self, handler)
        handler(u'--></style>')


class HtmlPreNode(HtmlNode):
    """
    <pre> ... </pre>
    """
    html_tagname = 'pre'

    def process_params(self, params):
        self.__open_tag = HtmlTag()
        self.__open_tag.children = params

    def output(self, handler):
        self.__open_tag.output(handler)
        Token.output(self, handler)
        handler('</pre>')


class HtmlTextareaNode(HtmlNode):
    """
    <textarea> ... </textarea>
    """
    html_tagname = 'textarea'

    def process_params(self, params):
        self.__open_tag = HtmlTag()
        self.__open_tag.children = params

    def output(self, handler):
        self.__open_tag.output(handler)
        Token.output(self, handler)
        handler('</textarea>')



__HTML_EXTENSION_MAPPINGS = {
        'html-doctype': HtmlDocType,
        'html-entity': HtmlEntity,
        'html-cdata': HtmlCDATA,
        'html-comment': HtmlComment,
        'html-tag': HtmlTag,
        'html-tag-name': HtmlTagName,
        'html-end-tag': HtmlEndTag,
        'html-tag-end-sign': HtmlTagEndSign,
        'html-tag-attribute': HtmlTagAttribute,
        'html-tag-whitespace': HtmlTagWhitespace,
        'html-tag-attribute-key': HtmlTagAttributeName,
        'html-tag-attribute-value': HtmlTagAttributeValue,
        'html-content': HtmlContent,
        'html-whitespace': HtmlWhiteSpace,
}


def _add_html_parser_extensions(tree):
    """
    Patch (some) nodes in the parse tree, to get the HTML parser functionality.
    """
    for node in tree.children:
        if isinstance(node, Token):
            if node.name in __HTML_EXTENSION_MAPPINGS:
                node.__class__ = __HTML_EXTENSION_MAPPINGS[node.name]
                if hasattr(node, 'init_extension'):
                    node.init_extension()

            _add_html_parser_extensions(node)


def _nest_elements(tree):
    """
    Example:
    Replace (<script>, content, </script>) nodes by a single node, moving the
    child nodes to the script's content.
    """
    block_elements1 = {
        'html-start-conditional-comment': ('html-end-conditional-comment', HtmlConditionalComment),
    }
    nest_block_level_elements(tree, block_elements1, [Token], lambda c: c.name)

    # Read as: move the content between:
        # element of this class, with this html_tagname, and
        # element of the other class, with the other html_tagname,
    # to a new parse node of the latter class.
    block_elements2 = {
        (False, HtmlTag, 'script'): ((False, HtmlEndTag, 'script'),  HtmlScriptNode),
        (False, HtmlTag, 'style'): ((False, HtmlEndTag, 'style'),  HtmlStyleNode),
        (False, HtmlTag, 'pre'): ((False, HtmlEndTag, 'pre'),  HtmlPreNode),
        (False, HtmlTag, 'textarea'): ((False, HtmlEndTag, 'textarea'),  HtmlTextareaNode),
    }

    nest_block_level_elements(tree, block_elements2, [HtmlTag, HtmlEndTag],
            lambda c: (c.is_closing_html_tag, c.__class__, c.html_tagname) )


# ==================================[  HTML Tree manipulations ]================================


def _merge_content_nodes(tree, context):
    """
    Concatenate whitespace and content nodes.
    e.g. when the we have "<p>...{% trans "</p>" %}" these nodes will be
         concatenated into one single node. (A preprocessed translation is a
         HtmlContent node)
    The usage in the example above is abuse, but in case of {% url %} and
    {% trans %} blocks inside javascript code, we want them all to be
    concatenated in order to make it possible to check the syntax of the
    result.
    e.g. "alert('{% trans "some weird characters in here: ',! " %}');"

    When insert_debug_symbols is on, only apply concatenation inside CSS and
    Javascript nodes. We want to keep the {% trans %} nodes in <body/> for
    adding line/column number annotations later on.
    """
    def apply(tree):
        last_child = None

        for c in tree.children[:]:
            if isinstance(c, HtmlContent):
                # Second content node (following another content node)
                if last_child:
                    for i in c.children:
                        last_child.children.append(i)
                    tree.children.remove(c)
                # Every first content node
                else:
                    last_child = c
                    last_child.__class__ = HtmlContent
            else:
                last_child = None

        # Apply recursively
        for c in tree.children:
            if isinstance(c, Token):
                _merge_content_nodes(c, context)

    # Concatenate nodes
    if context.insert_debug_symbols:
        # In debug mode: only inside script/style nodes
        for n in tree.child_nodes_of_class([ HtmlStyleNode, HtmlScriptNode ]):
            apply(n)
    else:
        apply(tree)


def _remove_whitespace_around_html_block_level_tags(tree):
    whitespace_elements = []
    after_block_level_element = False

    for c in tree.children[:]:
        # If we find a block level element
        if (isinstance(c, HtmlTag) or isinstance(c, HtmlEndTag)) and c.html_tagname in __HTML_BLOCK_LEVEL_ELEMENTS:
            after_block_level_element = True

            # remove all whitespace before
            for w in whitespace_elements:
                tree.children.remove(w)
            whitespace_elements = []

            # Also, *inside* the block level element, remove whitespace at the
            # beginning and before the end
            while len(c.children) and isinstance(c.children[0], HtmlWhiteSpace):
                c.children = c.children[1:]
            while len(c.children) and isinstance(c.children[-1], HtmlWhiteSpace):
                c.children = c.children[:-1]

        # If we find a whitespace
        elif isinstance(c, HtmlWhiteSpace):
            if after_block_level_element:
                # Remove whitespace after.
                tree.children.remove(c)
            else:
                whitespace_elements.append(c)

        # Something else: reset state
        else:
            whitespace_elements = []
            after_block_level_element = False

        # Recursively
        if isinstance(c, Token):
            _remove_whitespace_around_html_block_level_tags(c)


def _compress_whitespace(tree):
    # Don't compress in the following tags
    dont_enter = [ HtmlScriptNode, HtmlStyleNode, HtmlPreNode, HtmlTextareaNode ]

    for c in tree.children:
        if isinstance(c, HtmlWhiteSpace):
            c.compress()
        elif isinstance(c, Token) and not any([ isinstance(c, t) for t in dont_enter ]):
            _compress_whitespace(c)


def _remove_empty_class_attributes(tree):
    """
    For all the HTML tags which have empty class="" attributes,
    remove the attribute.
    """
    # For every HTML tag
    for tag in tree.child_nodes_of_class([ HtmlTag ]):
        for a in tag.child_nodes_of_class([ HtmlTagAttribute ]):
            if a.attribute_name == 'class' and a.attribute_value.output_as_string() in ('', '""', "''"):
                tag.children.remove(a)


def _turn_comments_to_content_in_js_and_css(tree):
    for c in tree.child_nodes_of_class([ HtmlStyleNode, HtmlScriptNode ]):
        for c2 in c.child_nodes_of_class([ HtmlCDATA, HtmlComment ]):
            c2.__class__ = HtmlContent


def _remove_comments(tree):
    tree.remove_child_nodes_of_class(HtmlComment)


def _merge_nodes_of_type(tree, type, dont_enter):
    """
    Merge nodes of this type into one node.
    """
    # Find all internal js nodes
    js_nodes = [ j for j in tree.child_nodes_of_class([type], dont_enter=dont_enter) if not j.is_external ]

    if js_nodes:
        first = js_nodes[0]

        # Move all js code from the following js nodes in the first one.
        for js in js_nodes[1:]:
            # Move js content
            first.children = first.children + js.children
            js.children = []

        # Remove all empty javascript nodes
        tree.remove_child_nodes(js_nodes[1:])


# ==================================[  HTML validation ]================================

def _validate_html_tags(tree):
    """
    Check whether all HTML tags exist.
    """
    for tag in tree.child_nodes_of_class([ HtmlTag ]):
        if tag.html_tagname not in __ALL_HTML_TAGS:
            # Ignore html tags in other namespaces:
            # (Like e.g. <x:tagname />, <fb:like .../>)
            if not ':' in tag.html_tagname:
                raise CompileException(tag, 'Unknown HTML tag: <%s>' % tag.html_tagname)


def _validate_html_attributes(tree):
    """
    Check whether HTML tags have no invalid or double attributes.
    """
    for tag in tree.child_nodes_of_class([ HtmlTag ]):
        # Ignore tags from other namespaces.
        if not ':' in tag.html_tagname:
            # Check for double attributes
            attr_list=[]

            if not len(list(tag.child_nodes_of_class([ DjangoTag ]))):
                # TODO XXX:  {% if ... %} ... {% endif %} are not yet groupped in an DjangoIfNode, which means
                # that the content of the if-block is still a child of the parent. For now, we simply
                # don't check in these cases.
                for a in tag.child_nodes_of_class([ HtmlTagAttribute ], dont_enter=[ DjangoTag ]):
                    if a.attribute_name in attr_list:
                        raise CompileException(tag, 'Attribute "%s" defined more than once for <%s> tag' %
                                        (a.attribute_name, tag.html_tagname))
                    attr_list.append(a.attribute_name)

            # Check for invalid attributes
            for a in tag.html_attributes:
                if ':' in a or a.startswith('data-'):
                    # Don't validate tagnames from other namespaces, or HTML5 data- attributes
                    continue

                elif a in __HTML_ATTRIBUTES['_']:
                    continue

                elif tag.html_tagname in __HTML_ATTRIBUTES and a in __HTML_ATTRIBUTES[tag.html_tagname]:
                    continue

                else:
                    raise CompileException(tag, 'Invalid HTML attribute "%s" for <%s> tag' % (a, tag.html_tagname))


def _ensure_type_in_scripts(tree):
    """
    <script> should have type="text/javascript"
    """
    for tag in tree.child_nodes_of_class([ HtmlTag ]):
        if tag.html_tagname == 'script':
            type_ = tag.html_attributes.get('type', None)
            if not bool(type_) or not type_.output_as_string() == u'"text/javascript"':
                raise CompileException(tag, '<script> should have type="text/javascript"')


def _ensure_type_in_css(tree):
    """
    <style> should have type="text/css"
    """
    for tag in tree.child_nodes_of_class([ HtmlTag ]):
        if tag.html_tagname == 'style':
            type_ = tag.html_attributes.get('type', None)
            if not bool(type_) or not type_.output_as_string() == u'"text/css"':
                raise CompileException(tag, '<style> should have type="text/css"')


def _ensure_href_in_hyperlinks(tree):
    """
    Throw error if no href found in hyperlinks.
    """
    for tag in tree.child_nodes_of_class([ HtmlTag ]):
        if tag.html_tagname == 'a':
            href = tag.html_attributes.get('href', None)
            if href:
                attr = href.output_as_string()
                if attr in ('', '""', "''"):
                    raise CompileException(tag, 'Empty href-attribute not allowed for hyperlink')

                # Disallow javascript: links
                if any([ attr.startswith(x) for x in ('javascript:', '"javascript:', "'javascript:")]):
                    raise CompileException(tag, 'Javascript hyperlinks not allowed.')

            else:
                raise CompileException(tag, 'href-attribute required for hyperlink')


def _ensure_alt_attribute(tree):
    """
    For every image, check if alt attribute exists missing.
    """
    for tag in tree.child_nodes_of_class([ HtmlTag ]):
        if tag.html_tagname == 'img':
            if not tag.html_attributes.get('alt', None):
                raise CompileException(tag, 'alt-attribute required for image')


def _nest_all_elements(tree):
    """
    Manipulate the parse tree by combining all opening and closing html nodes,
    to reflect the nesting of HTML nodes in the tree.
    So where '<p>' and '</p>' where two independent siblings in the source three,
    they become one now, and everything in between is considered a child of this tag.
    """
    # NOTE: this does not yet combile unknown tags, like <fb:like/>,
    #       maybe it's better to replace this code by a more dynamic approach.
    #       Or we can ignore them, like we do know, because we're not unsure
    #       how to thread them.
    def _create_html_tag_node(name):
        class tag_node(HtmlTagPair):
            html_tagname = ''
            def process_params(self, params):
                # Create new node for the opening html tag
                self._open_tag = HtmlTag()
                self._open_tag.children = params

                # Copy line/column number information
                self._open_tag.line = self.line
                self._open_tag.column = self.column
                self._open_tag.path = self.path

            @property
            def open_tag(self):
                return self._open_tag

            def output(self, handler):
                self._open_tag.output(handler)
                Token.output(self, handler)
                handler('</%s>' % name)

        tag_node.__name__ = name
        tag_node.html_tagname = name
        return tag_node

    # Parse all other HTML tags, (useful for validation, it checks whether
    # every opening tag has a closing match. It doesn't hurt, but also doesn't
    # make much sense to enable this in a production environment.)
    block_elements2 = { }

    for t in __ALL_HTML_TAGS:
        block_elements2[(False, HtmlTag, t)] = ((False, HtmlEndTag, t), _create_html_tag_node(t))

    nest_block_level_elements(tree, block_elements2, [HtmlTag, HtmlEndTag],
            lambda c: (c.is_closing_html_tag, c.__class__, c.html_tagname) )


def _check_no_block_level_html_in_inline_html(tree, options):
    """
    Check whether no block level HTML elements, like <div> are nested inside
    in-line HTML elements, like <span>. Raise CompileException otherwise.
    """
    def check(node, inline_tag=None):
        for c in node.children:
            if isinstance(c, HtmlNode) and hasattr(c.__class__, 'html_tagname'):
                if inline_tag and c.__class__.html_tagname in __HTML_BLOCK_LEVEL_ELEMENTS:
                    raise CompileException(c, 'Improper nesting of HTML tags. Block level <%s> node should not appear inside inline <%s> node.' % (c.__class__.html_tagname, inline_tag))

                if c.__class__.html_tagname in __HTML_INLINE_LEVEL_ELEMENTS:
                    check(c, c.__class__.html_tagname)
                elif c.__class__.html_tagname in __HTML_INLINE_BLOCK_ELEMENTS:
                    # This are block level tags, but can only contain inline level elements,
                    # therefor, consider as in-line from now on.
                    check(c, c.__class__.html_tagname)
                else:
                    check(c, inline_tag)
            elif isinstance(c, DjangoContainer):
                check(c, inline_tag)

    check(tree)


def _check_for_unmatched_closing_html_tags(tree):
    for tag in tree.child_nodes_of_class([ HtmlEndTag ]):
        # NOTE: end tags may still exist for unknown namespaces because the
        #       current implementation does not yet combile unknown start and
        #       end tags.
        if not ':' in tag.html_tagname:
            raise CompileException(tag, 'Unmatched closing </%s> tag' % tag.html_tagname)


# ==================================[  Advanced script/css manipulations ]================================


from django.conf import settings
from django.core.urlresolvers import reverse
from template_preprocessor.core.css_processor import compile_css
from template_preprocessor.core.js_processor import compile_javascript

MEDIA_URL = settings.MEDIA_URL
STATIC_URL = getattr(settings, 'STATIC_URL', '')



def _merge_internal_javascript(tree):
    """
    Group all internal javascript code in the first javascript block.
    NOTE: but don't move scripts which appear in a conditional comment.
    """
    _merge_nodes_of_type(tree, HtmlScriptNode, dont_enter=[HtmlConditionalComment])


def _merge_internal_css(tree):
    """
    Group all internal CSS code in the first CSS block.
    """
    _merge_nodes_of_type(tree, HtmlStyleNode, dont_enter=[HtmlConditionalComment])


def _pack_external_javascript(tree, context):
    """
    Pack external javascript code. (between {% compress %} and {% endcompress %})
    """
    # For each {% compress %}
    for compress_tag in tree.child_nodes_of_class([ DjangoCompressTag ]):
        # Respect the order of the scripts
        scripts_in_pack = []

        # Find each external <script /> starting with the MEDIA_URL or STATIC_URL
        for script in compress_tag.child_nodes_of_class([ HtmlScriptNode ]):
            if script.is_external:
                source = script.script_source
                if ((MEDIA_URL and source.startswith(MEDIA_URL)) or
                        (STATIC_URL and source.startswith(STATIC_URL)) or
                        is_remote_url(source)):
                    # Add to list
                    scripts_in_pack.append(source)
                    check_external_file_existance(script, source)


        if scripts_in_pack:
            # Remember which media files were linked to this cache,
            # and compile the media files.
            new_script_url = context.compile_js_files(compress_tag, scripts_in_pack)

            # Replace the first external script's url by this one.
            # Remove all other external script files
            first = True
            for script in list(compress_tag.child_nodes_of_class([ HtmlScriptNode ])):
                # ! Note that we made a list of the child_nodes_of_class iterator,
                #   this is required because we are removing childs from the list here.
                if script.is_external:
                    source = script.script_source
                    if ((MEDIA_URL and source.startswith(MEDIA_URL)) or
                                (STATIC_URL and source.startswith(STATIC_URL)) or
                                is_remote_url(source)):
                        if first:
                            # Replace source
                            script.script_source = new_script_url
                            first = False
                        else:
                            compress_tag.remove_child_nodes([script])


def _pack_external_css(tree, context):
    """
    Pack external CSS code. (between {% compress %} and {% endcompress %})
    Replaces <link type="text/css" rel="stylesheet" media="..." />

    This will bundle all stylesheet in the first link tag. So it's better
    to use multiple {% compress %} tags if you have several values for media.
    """
    def is_external_css_tag(tag):
        return tag.html_tagname == 'link' and \
                tag.get_html_attribute_value_as_string('type') == 'text/css' and \
                tag.get_html_attribute_value_as_string('rel') == 'stylesheet'

    # For each {% compress %}
    for compress_tag in tree.child_nodes_of_class([ DjangoCompressTag ]):
        # Respect the order of the links
        css_in_pack = []

        # Find each external <link type="text/css" /> starting with the MEDIA_URL
        for tag in compress_tag.child_nodes_of_class([ HtmlTag ]):
            if is_external_css_tag(tag):
                source = tag.get_html_attribute_value_as_string('href')
                if ((MEDIA_URL and source.startswith(MEDIA_URL)) or
                        (STATIC_URL and source.startswith(STATIC_URL)) or
                        is_remote_url(source)):
                    # Add to list
                    css_in_pack.append( { 'tag': tag, 'source': source } )
                    check_external_file_existance(tag, source)

        # Group CSS only when they have the same 'media' attribute value
        while css_in_pack:
            # Place first css include in current pack
            first_tag = css_in_pack[0]['tag']
            media = first_tag.get_html_attribute_value_as_string('media')

            css_in_current_pack = [ css_in_pack[0]['source'] ]
            css_in_pack = css_in_pack[1:]

            # Following css includes with same media attribute
            while css_in_pack and css_in_pack[0]['tag'].get_html_attribute_value_as_string('media') == media:
                # Remove this tag from the HTML tree (not needed anymore)
                compress_tag.remove_child_nodes([ css_in_pack[0]['tag'] ])

                # Remember source
                css_in_current_pack.append(css_in_pack[0]['source'])
                css_in_pack = css_in_pack[1:]

            # Remember which media files were linked to this cache,
            # and compile the media files.
            new_css_url = context.compile_css_files(compress_tag, css_in_current_pack)

            # Update URL for first external CSS node
            first_tag.set_html_attribute('href', new_css_url)


# ==================================[  Debug extensions ]================================

class Trace(Token):
    def __init__(self, original_node):
        Token.__init__(self, line=original_node.line, column=original_node.column, path=original_node.path)
        self.original_node = original_node

class BeforeDjangoTranslatedTrace(Trace): pass
class AfterDjangoTranslatedTrace(Trace): pass
class BeforeDjangoPreprocessedUrlTrace(Trace): pass
class AfterDjangoPreprocessedUrlTrace(Trace): pass


def _insert_debug_trace_nodes(tree, context):
    """
    If we need debug symbols. We have to insert a few traces.
    DjangoTranslated and DjangoPreprocessedUrl will are concidered content
    during the HTML parsing and will disappear.
    We add a trace before and after this nodes. if they still match after
    HTML parsing (which should unless in bad cases like "<p>{%trans "</p>" %}")
    then we can insert debug symbols.
    """
    def insert_trace(cls, before_class, after_class):
        for trans in tree.child_nodes_of_class([ cls ]):
            trans_copy = deepcopy(trans)

            trans.children.insert(0, before_class(trans_copy))
            trans.children.append(after_class(trans_copy))

    insert_trace(DjangoTranslated, BeforeDjangoTranslatedTrace, AfterDjangoTranslatedTrace)
    insert_trace(DjangoPreprocessedUrl, BeforeDjangoPreprocessedUrlTrace, AfterDjangoPreprocessedUrlTrace)


def _insert_debug_symbols(tree, context):
    """
    Insert useful debugging information into the template.
    """
    # Find head/body nodes
    body_node = None
    head_node = None

    for tag in tree.child_nodes_of_class([ HtmlTagPair ]):
        if tag.html_tagname == 'body':
            body_node = tag

        if tag.html_tagname == 'head':
            head_node = tag

    # Give every node a debug reference
    tag_references = { }

    def create_references():
        ref_counter = [0]
        for tag in body_node.child_nodes_of_class([ HtmlTagPair, HtmlTag ]):
                tag_references[tag] = ref_counter[0]
                ref_counter[0] += 1
    create_references()

    def apply_tag_refences():
        for tag, ref_counter in tag_references.items():
            if isinstance(tag, HtmlTagPair):
                tag.open_tag.set_html_attribute('d:ref', ref_counter)
            else:
                tag.set_html_attribute('d:ref', ref_counter)

    # Add template source of this node as an attribute of it's own node.
    # Only for block nodes inside <body/>
    if body_node:
        # The parent node would contain the source of every child node as
        # well, but we do not want to send the same source 100times to the browser.
        # Therefor we add hooks for every tag, and replace it by pointers.

        apply_source_list = [] # (tag, source)

        for tag in body_node.child_nodes_of_class([ HtmlTagPair ]):
            def output_hook(tag):
                return '{$ %s $}' % tag_references[tag]

            hooks = {
                    HtmlTagPair: output_hook,
                    HtmlTag: output_hook
                    }

            apply_source_list.append((tag.open_tag, tag.output_as_string(hook_dict=hooks)))

        for tag, source in apply_source_list:
            tag.set_html_attribute('d:s', source)

    # For every HTML node, add the following attributes:
    #  d:t="template.html"
    #  d:l="line_number"
    #  d:c="column_number"
    #  d:href="{% url ... %}"
    def add_template_info(tag):
        tag.set_html_attribute('d:t', tag.path)
        tag.set_html_attribute('d:l', tag.line)
        tag.set_html_attribute('d:c', tag.column)

        # For every hyperlink, like <a href="{% url ... %}">, add an attribute d:href="...",
        # where this contains the original url tag, without escaping.
        if tag.html_tagname == 'a':
            href = tag.html_attributes.get('href', None)

            if href:
                for url in href.child_nodes_of_class([ DjangoUrlTag ]):
                    tag.set_html_attribute('d:href', url.output_as_string())

                for url in href.child_nodes_of_class([ DjangoPreprocessedUrl ]):
                    tag.set_html_attribute('d:href', url.original_urltag.output_as_string())

    for tag in tree.child_nodes_of_class([ HtmlTag ]):
        add_template_info(tag)

    for tag in tree.child_nodes_of_class([ HtmlTagPair ]):
        add_template_info(tag.open_tag)

    # Surround every {% trans %} block which does not appear into Javascript or Css
    # by <span d:l="..." d:c="..." d:o="original_string..." ...>
    # Note that we can do this only when the traces before and after {% trans %}
    # are still matching. This is only when the HTML parser did not mess up
    # the parse tree like in: "<p>{% trans "</p>" %}"
    def find_matching_traces(tree, is_inline=False):
        last_trace = None

        for node in tree.children:
            if (last_trace and isinstance(last_trace, BeforeDjangoTranslatedTrace) and
                        isinstance(node, AfterDjangoTranslatedTrace) and last_trace.original_node == node.original_node):
                original_node = node.original_node
                tagname = 'tp:trans'
                last_trace.children = [ '<%s tp:c="%s" tp:l="%s" tp:t="%s" tp:s="%s">' % (
                            tagname,
                            original_node.column, original_node.line, original_node.path,
                            xml_escape(original_node.translation_info.string)
                            ) ]
                node.children = [ '</%s>' % tagname ]

            if isinstance(node, Trace):
                last_trace = node

            # Recursively find matching traces in
            if isinstance(node, HtmlTagPair):
                find_matching_traces(node, is_inline or node.open_tag.is_inline)

            elif isinstance(node, Token) and not any(isinstance(node, c) for c in (Trace, HtmlScriptNode, HtmlStyleNode, HtmlTag)):
                find_matching_traces(node, is_inline)

#    if body_node:
#        find_matching_traces(body_node)

#  TODO: don't place string inside custom tags, as that can destroy the CSS
#  layout very much, but add these properties to an attribute of the parent
#  node, somewhere... OR! bring both the beginning and end markers to the
#  client, like <tp:trans-start ...></tp:trans-start> ..... <tp:trans-end></tp:trans-end>

    # For every <html> node, insert a <script>-node at the end, which points
    # to the debug script of the preprocessor for handling this information.
    if body_node:
        body_node.children.append('<script type="text/javascript" src="/static/template_preprocessor/js/debug.js"></script>')

    if head_node:
        head_node.children.append('<link type="text/css" rel="stylesheet" href="/static/template_preprocessor/css/debug.css" />')

    # Add {{ template_preprocessor_context_id }} variable to body.
    # If this variable exist in the context during rendering, it means that
    # the context will be remained in cache by the template loader, and that
    # javascript can do a reload call to automatically reload the page on
    # the first change in any related source file.
    if body_node:
        body_node.children.append('<span style="display:none;" class="tp-context-id">' +
                        '{{ template_preprocessor_context_id }}</span>')

    # Apply tag references as attributes now. (The output could be polluted if we did this earlier)
    apply_tag_refences()


# ==================================[  HTML Parser ]================================


def compile_html_string(html_string, path=''):
    """
    Compile a html string
    """
    # First, create a tree to begin with
    tree = Token(name='root', line=1, column=1, path=path)
    tree.children = [ html_string ]

    # Tokenize
    tokenize(tree, __HTML_STATES, [Token] )

    from template_preprocessor.core.context import Context
    context = Context(path)
    _process_html_tree(tree, context)

    # Output
    return tree.output_as_string()


def compile_html(tree, context):
    """
    Compile the html in content nodes
    """
    # If we need debug symbols. We have to insert a few traces.
    if context.insert_debug_symbols:
        _insert_debug_trace_nodes(tree, context)

    # Parse HTML code in parse tree (Note that we don't enter DjangoRawTag)
    tokenize(tree, __HTML_STATES, [DjangoContent], [DjangoContainer ])
    _process_html_tree(tree, context)


def _process_html_tree(tree, context):
    options = context.options

    # Add HTML parser extensions
    _add_html_parser_extensions(tree)

    # All kind of HTML validation checks
    if options.validate_html:
        # Methods to execute before nesting everything
        _validate_html_tags(tree)
        _ensure_type_in_scripts(tree)
        _ensure_type_in_css(tree)
        _validate_html_attributes(tree)
        _ensure_href_in_hyperlinks(tree)
        _ensure_alt_attribute(tree)
        # TODO: check for deprecated HTML tags also

    # Remove empty class="" parameter
    if options.remove_empty_class_attributes:
        _remove_empty_class_attributes(tree)
        apply_method_on_parse_tree(tree, HtmlTag, 'remove_whitespace_in_html_tag')

    _nest_elements(tree)

    # All kind of HTML validation checks, part II
    if options.validate_html:
        # Nest all elements
        _nest_all_elements(tree)

        # Validate nesting.
        _check_no_block_level_html_in_inline_html(tree, options)
        _check_for_unmatched_closing_html_tags(tree)

    # Turn comments into content, when they appear inside JS/CSS and remove all other comments
    _turn_comments_to_content_in_js_and_css(tree)
    _remove_comments(tree)

    # Merge all internal javascript code
    if options.merge_internal_javascript:
        _merge_internal_javascript(tree)

    # Merge all internal CSS code
    if options.merge_internal_css:
        _merge_internal_css(tree)

    # Need to be done before JS or CSS compiling.
    _merge_content_nodes(tree, context)

    # Pack external Javascript
    if options.pack_external_javascript:
        _pack_external_javascript(tree, context)

    # Pack external CSS
    if options.pack_external_css:
        _pack_external_css(tree, context)

    # Compile javascript
    if options.compile_javascript:
        for js_node in tree.child_nodes_of_class([ HtmlScriptNode ]):
            if not js_node.is_external:
                #print 'compiling'
                #print js_node._print()
                compile_javascript(js_node, context)

    # Compile CSS
    if options.compile_css:
        # Document-level CSS
        for css_node in tree.child_nodes_of_class([ HtmlStyleNode ]):
            compile_css(css_node, context)

        # In-line CSS.
            # TODO: this would work, if attribute_value didn't contain the attribute quotes.
        '''
        for attr in tree.child_nodes_of_class([ HtmlTagAttribute ]):
            if attr.attribute_name == 'style':
                att.attribute_value = compile_css(attr.attribute_value)
        '''


    ## TODO: remove emty CSS nodes <style type="text/css"><!-- --></style>

    # Insert DEBUG symbols (for bringing line/column numbers to web client)
    if context.insert_debug_symbols:
        _insert_debug_symbols(tree, context)

    # Whitespace compression
    if options.whitespace_compression:
        _compress_whitespace(tree)
        _remove_whitespace_around_html_block_level_tags(tree)

