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
import string
import codecs
import os
from copy import deepcopy
from django.conf import settings
from hashlib import md5


__HTML_BLOCK_LEVEL_ELEMENTS = ('html', 'head', 'body', 'meta', 'script', 'noscript', 'p', 'div', 'ul', 'ol', 'dl', 'dt', 'dd', 'li', 'table', 'td', 'tr', 'th', 'thead', 'tfoot', 'tbody', 'br', 'link', 'title', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'form', 'object', 'base', 'iframe', 'fieldset', 'code', 'blockquote', 'legend', 'pre', ) # TODO: complete
__HTML_INLINE_LEVEL_ELEMENTS = ('span', 'a', 'b', 'i', 'em', 'del', 'ins', 'strong', 'select', 'label', 'q', 'sub', 'sup', 'small', 'sub', 'sup', 'option', 'abbr', 'img', 'input', 'hr', 'param', 'button', 'caption', 'style', 'textarea', 'colgroup', 'col', 'samp' )

    # TODO: 'img', 'object' 'button', 'td' and 'th' are inline-block

        # HTML tags consisting of separate open and close tag.
__ALL_HTML_TAGS = __HTML_BLOCK_LEVEL_ELEMENTS + __HTML_INLINE_LEVEL_ELEMENTS

__DEPRECATED_HTML_TAGS = ('i', 'b', 'u' )

__HTML_ATTRIBUTES = {
    # Valid for every HTML tag
    '_': ('id', 'class', 'style', 'lang', 'xmlns', 'title', 'xml:lang'),

    'a': ('href', 'target', 'rel', 'accesskey', 'name', 'share_url'), # share_url is not valid, but used in the facebook share snipped.
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
    'iframe': ('src', 'name', 'height', 'width', 'marginwidth', 'marginheight', 'scrolling', 'frameborder', ),
    'param': ('name', 'value', ),
    'table': ('cellpadding', 'cellspacing', 'summary', 'width', ),
    'p': ('align', ), # Deprecated
    'embed': ('src', 'allowscriptaccess', 'height', 'width', 'allowfullscreen', 'type', ),
}

# TODO: check whether forms have {% csrf_token %}
# TODO: check whether all attributes are valid.


__HTML_STATES = {
    'root' : State(
            # conditional comments
            State.Transition(r'<!--\[if', (StartToken('html-start-conditional-comment'), Record(), Shift(), Push('conditional-comment'), )),
            State.Transition(r'<!\[endif\]-->', (StartToken('html-end-conditional-comment'), Record(), Shift(), StopToken(), )),
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
            State.Transition(r'[\s\w]+', (Record(), Shift(), )),
            State.Transition(r'\]>', (Record(), Shift(), Pop(), StopToken(), )),

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
        self.add_attribute(name, '"%s"' % attribute_value) # TODO: XML escape


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


class HtmlTagWhitespace(HtmlNode):
    pass

class HtmlTagAttributeName(HtmlNode):
    pass


class HtmlTagAttributeValue(HtmlNode):
    def init_extension(self):
        self.__double_quotes = False

    def ensure_double_quotes(self):
        """
        Always output double quotes
        TODO: this does not always work. Causes sometimes double double-quotes
        """
        # Remove quotes if they already exist in child nodes
        if len(self.children) >= 1:
            if isinstance(self.children[0], basestring) and isinstance(self.children[-1], basestring):
                if self.children[0][:1] in ('"', "'"):
                    self.children[0] = self.children[0][1:]

                if self.children[-1][-1:] in ('"', "'"):
                    self.children[-1] = self.children[0][:-1]

            # Append double quotes in output
            self.__double_quotes = True

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
        self.__attrs['src='] = '"%s"' % value # TODO: XML escape

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


def _merge_content_nodes(tree):
    """
    Merge whitespace and content nodes.
    """
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
            _merge_content_nodes(c)


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


def _fill_in_alt_and_title_attributes(tree):
    """
    For every image, insert alt and title attributes if they are missing.
    """
    for tag in tree.child_nodes_of_class([ HtmlTag ]):
        if tag.html_tagname == 'img':
            attributes = tag.html_attributes

            alt = attributes.get('alt') or attributes.get('title') or None
            has_alt = bool(alt) and not alt.output_as_string() in ('', '""', "''")

            if has_alt:
                alt = deepcopy(alt)
            else:
                alt = HtmlTagAttributeValue();
                alt.init_extension()
                alt.children = [ '""' ]

            if not 'alt' in attributes:
                tag.add_attribute('alt', alt)

            if has_alt and not 'title' in attributes:
                tag.add_attribute('title', alt)


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
            # Allow names <x:tagname />, this are data nodes.
            if not tag.html_tagname.startswith('x:'):
                raise CompileException(tag, 'Unknown HTML tag: <%s>' % tag.html_tagname)


def _validate_html_attributes(tree):
    """
    Check whether HTML tags have no invalid or double attributes.
    """
    for tag in tree.child_nodes_of_class([ HtmlTag ]):
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
            if ':' in a:
                # Don't validate tagnames from other namespaces.
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
    """
    def _create_html_tag_node(name):
        class tag_node(HtmlNode):
            html_tagname = ''
            def process_params(self, params):
                self.__open_tag = HtmlTag()
                self.__open_tag.children = params

            @property
            def open_tag(self):
                return self.__open_tag

            def output(self, handler):
                self.__open_tag.output(handler)
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
                elif c.__class__.html_tagname in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
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
        raise CompileException(tag, 'Unmatched closing </%s> tag' % tag.html_tagname)


# ==================================[  Advanced script/css manipulations ]================================


from django.conf import settings
from django.core.urlresolvers import reverse
from template_preprocessor.core.css_processor import compile_css
from template_preprocessor.core.js_processor import compile_javascript

import codecs
import os

__js_compiled = { }
__css_compiled = { }

MEDIA_ROOT = settings.MEDIA_ROOT
MEDIA_URL = settings.MEDIA_URL
MEDIA_CACHE_DIR = settings.MEDIA_CACHE_DIR
MEDIA_CACHE_URL = settings.MEDIA_CACHE_URL
STATIC_URL = getattr(settings, 'STATIC_URL', '')


def _create_directory_if_not_exists(directory):
    if not os.path.exists(directory):
        os.mkdir(directory)


def _get_media_source_from_url(url):
    """
    For a given media/static URL, return the matching full path in the media/static directory
    """
    if MEDIA_URL and url.startswith(MEDIA_URL):
        return os.path.join(MEDIA_ROOT, url[len(MEDIA_URL):].lstrip('/'))

    elif STATIC_URL and url.startswith(STATIC_URL):
        from django.contrib.staticfiles.finders import find
        path = url[len(STATIC_URL):].lstrip('/')
        return find(path)


def _check_external_file_existance(node, url):
    """
    Check whether we have a matching file in our media/static directory for this URL.
    Raise exception if we don't.
    """
    complete_path = _get_media_source_from_url(url)

    if not complete_path or not os.path.exists(complete_path):
        if MEDIA_URL and url.startswith(MEDIA_URL):
            raise CompileException(node, 'Missing external media file (%s)' % url)

        elif STATIC_URL and url.startswith(STATIC_URL):
            raise CompileException(node, 'Missing external static file (%s)' % url)


def _compile_js_files(hash, media_files):
    from template_preprocessor.core.js_processor import compile_javascript_string

    if hash in __js_compiled:
        compiled_path = __js_compiled[hash]
    else:
        print 'Compiling media: ', ', '.join(media_files)
        # Compile script
            # 1. concatenate and compile all scripts
        source = u'\n'.join([
                    compile_javascript_string(codecs.open(_get_media_source_from_url(p), 'r', 'utf-8').read(), p)
                    for p in media_files ])

            # 2. Store in media dir
        compiled_path = '%s.js' % hash
        _create_directory_if_not_exists(MEDIA_CACHE_DIR)
        codecs.open(os.path.join(MEDIA_CACHE_DIR, compiled_path), 'w', 'utf-8').write(source)

        # Save
        __js_compiled[hash] = compiled_path

    return os.path.join(MEDIA_CACHE_URL, compiled_path)


def _compile_css_files(hash, media_files):
    from template_preprocessor.core.css_processor import compile_css_string

    if hash in __css_compiled:
        compiled_path = __css_compiled[hash]
    else:
        print 'Compiling media: ', ', '.join(media_files)
        # Compile CSS
            # 1. concatenate and compile all css files
        source = u'\n'.join([
                    compile_css_string(
                                codecs.open(_get_media_source_from_url(p), 'r', 'utf-8').read(),
                                os.path.join(MEDIA_ROOT, p),
                                url=os.path.join(MEDIA_URL, p))
                    for p in media_files ])

            # 2. Store in media dir
        compiled_path = '%s.css' % hash
        _create_directory_if_not_exists(MEDIA_CACHE_DIR)
        codecs.open(os.path.join(MEDIA_CACHE_DIR, compiled_path), 'w', 'utf-8').write(source)

        # Save
        __css_compiled[hash] = compiled_path

    return os.path.join(MEDIA_CACHE_URL, compiled_path)



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


def _pack_external_javascript(tree):
    """
    Pack external javascript code. (between {% compress %} and {% endcompress %})
    """
    # For each {% compress %}
    for pack_tag in tree.child_nodes_of_class([ DjangoCompressTag ]):
        # Respect the order of the scripts
        scripts_in_pack = []

        # Find each external <script /> starting with the MEDIA_URL
        for script in pack_tag.child_nodes_of_class([ HtmlScriptNode ]):
            if script.is_external:
                source = script.script_source
                if (MEDIA_URL and source.startswith(MEDIA_URL)) or (STATIC_URL and source.startswith(STATIC_URL)):
                    # Add to list
                    scripts_in_pack.append(source)
                    _check_external_file_existance(script, source)

        if scripts_in_pack:
            # Create a hash for all the scriptnames
            # And remember in cache
            scripts_in_pack = tuple(scripts_in_pack) # tuples are hashable
            hash = md5(''.join(scripts_in_pack)).hexdigest()

            # Remember which media files were linked to this cache,
            # and compile the media files.
            new_script_url = _compile_js_files(hash, scripts_in_pack)

            # Replace the first external script's url by this one.
            # Remove all other external script files
            first = True
            for script in list(pack_tag.child_nodes_of_class([ HtmlScriptNode ])):
                # ! Note that we made a list of the child_nodes_of_class iterator,
                #   this is required because we are removing childs from the list here.
                if script.is_external:
                    if script.script_source.startswith(MEDIA_URL):
                        if first:
                            # Replace source
                            script.script_source = new_script_url
                            first = False
                        else:
                            pack_tag.remove_child_nodes([script])


def _pack_external_css(tree):
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
    for pack_tag in tree.child_nodes_of_class([ DjangoCompressTag ]):
        # Respect the order of the links
        css_in_pack = []

        # Find each external <link type="text/css" /> starting with the MEDIA_URL
        for tag in pack_tag.child_nodes_of_class([ HtmlTag ]):
            if is_external_css_tag(tag):
                source = tag.get_html_attribute_value_as_string('href')
                if (MEDIA_URL and source.startswith(MEDIA_URL)) or (STATIC_URL and source.startswith(STATIC_URL)):
                    # Add to list
                    css_in_pack.append( { 'tag': tag, 'source': source } )
                    _check_external_file_existance(tag, source)

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
                pack_tag.remove_child_nodes([ css_in_pack[0]['tag'] ])

                # Remember source
                css_in_current_pack.append(css_in_pack[0]['source'])
                css_in_pack = css_in_pack[1:]

            # Create a hash for all concecutive CSS files with the same media attribute
            # And remember in cache
            css_in_current_pack = tuple(css_in_current_pack) # tuples are hashable
            hash = md5(''.join(css_in_current_pack)).hexdigest()

            # Remember which media files were linked to this cache,
            # and compile the media files.
            new_css_url = _compile_css_files(hash, css_in_current_pack)

            # Update URL for first external CSS node
            first_tag.set_html_attribute('href', new_css_url)


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

    from template_preprocessor.core.django_processor import PreProcessSettings
    options = PreProcessSettings()
    _process_html_tree(tree, options)

    # Output
    return tree.output_as_string()


def compile_html(tree, options):
    """
    Compile the html in content nodes
    """
    # Parse HTML code in parse tree (Note that we don't enter DjangoRawTag)
    tokenize(tree, __HTML_STATES, [DjangoContent], [DjangoContainer ])
    _process_html_tree(tree, options)


def _process_html_tree(tree, options):
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


    # Place double quotes around HTML attributes
    if options.ensure_quotes_around_html_attributes:
        # NOTE: Should be disabled by default. Still unreliable.
        apply_method_on_parse_tree(tree, HtmlTagAttributeValue, 'ensure_double_quotes')

    # Remove the comment node <!-- --> in CSS,
    _turn_comments_to_content_in_js_and_css(tree)

    # Merge all internal javascript code
    if options.merge_internal_javascript:
        _merge_internal_javascript(tree)

    # Merge all internal CSS code
    if options.merge_internal_css:
        _merge_internal_css(tree)

    # Whitespace compression
    if options.whitespace_compression:
        _compress_whitespace(tree)
        _remove_whitespace_around_html_block_level_tags(tree)

    # Ensure alt in <img alt="..." />
    if options.check_alt_and_title_attributes:
        _fill_in_alt_and_title_attributes(tree)

    # Need to be done before JS or CSS compiling.
    _merge_content_nodes(tree)

    # Pack external Javascript
    if options.pack_external_javascript:
        _pack_external_javascript(tree)

    # Pack external CSS
    if options.pack_external_css:
        _pack_external_css(tree)

    # Compile javascript
    if options.compile_javascript:
        for js_node in tree.child_nodes_of_class([ HtmlScriptNode ]):
            if not js_node.is_external:
                #print 'compiling'
                #print js_node._print()
                compile_javascript(js_node)

    # Compile CSS
    if options.compile_css:
        # Document-level CSS
        for css_node in tree.child_nodes_of_class([ HtmlStyleNode ]):
            compile_css(css_node)

        # In-line CSS.
            # TODO: this would work, if attribute_value didn't contain the attribute quotes.
        '''
        for attr in tree.child_nodes_of_class([ HtmlTagAttribute ]):
            if attr.attribute_name == 'style':
                compile_css(attr.attribute_value)
        '''


    ## TODO: remove emty CSS nodes <style type="text/css"><!-- --></style>

