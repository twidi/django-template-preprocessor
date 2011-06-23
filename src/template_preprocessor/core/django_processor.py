#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Django template preprocessor.
Author: Jonathan Slenders, City Live
"""

"""
Django parser for a template preprocessor.
------------------------------------------------------------------
Parses django template tags.
This parser will call the html/css/js parser if required.
"""

from django.conf import settings
from django.template import TemplateDoesNotExist
from django.utils.translation import ugettext as _, ungettext

from template_preprocessor.core.lexer import Token, State, StartToken, Shift, StopToken, Push, Pop, Error, Record, CompileException
from template_preprocessor.core.preprocessable_template_tags import get_preprocessable_tags, NotPreprocessable
from template_preprocessor.core.lexer_engine import nest_block_level_elements, tokenize
import re
from copy import deepcopy



__DJANGO_STATES = {
    'root' : State(
            # Start of django tag
            State.Transition(r'\{#', (StartToken('django-comment'), Shift(), Push('django-comment'))),
            State.Transition(r'\{%\s*comment\s*%\}', (StartToken('django-multiline-comment'), Shift(), Push('django-multiline-comment'))),
            State.Transition(r'\{%\s*', (StartToken('django-tag'), Shift(), Push('django-tag'))),
            State.Transition(r'\{{\s*', (StartToken('django-variable'), Shift(), Push('django-variable'))),

            # Content
            State.Transition(r'([^{]|%|{(?![%#{]))+', (StartToken('content'), Record(), Shift(), StopToken())),

            State.Transition(r'.|\s', (Error('Error in parser'),)),
        ),
    # {# .... #}
    'django-comment': State(
            State.Transition(r'#\}', (StopToken(), Shift(), Pop())),
            State.Transition(r'[^\n#]+', (Record(), Shift())),
            State.Transition(r'\n', (Error('No newlines allowed in django single line comment'), )),
            State.Transition(r'#(?!\})', (Record(), Shift())),

            State.Transition(r'.|\s', (Error('Error in parser: comment'),)),
        ),
    'django-multiline-comment': State(
            State.Transition(r'\{%\s*endcomment\s*%\}', (StopToken(), Shift(), Pop())), # {% endcomment %}
                    # Nested single line comments are allowed
            State.Transition(r'\{#', (StartToken('django-comment'), Shift(), Push('django-comment'))),
            State.Transition(r'[^{]+', (Record(), Shift(), )), # Everything except '{'
            State.Transition(r'\{(?!\{%\s*endcomment\s*%\}|#)', (Record(), Shift(), )), # '{' if not followed by '%endcomment%}'
        ),
    # {% tagname ... %}
    'django-tag': State(
            #State.Transition(r'([a-zA-Z0-9_\-\.|=:\[\]<>(),]+|"[^"]*"|\'[^\']*\')+', # Whole token as one
            State.Transition(r'([^\'"\s%}]+|"[^"]*"|\'[^\']*\')+', # Whole token as one
                                        (StartToken('django-tag-element'), Record(), Shift(), StopToken() )),
            State.Transition(r'\s*%\}', (StopToken(), Shift(), Pop())),
            State.Transition(r'\s+', (Shift(), )), # Skip whitespace

            State.Transition(r'.|\s', (Error('Error in parser: django-tag'),)),
        ),
    # {{ variable }}
    'django-variable': State(
            #State.Transition(r'([a-zA-Z0-9_\-\.|=:\[\]<>(),]+|"[^"]*"|\'[^\']*\')+',
            State.Transition(r'([^\'"\s%}]+|"[^"]*"|\'[^\']*\')+',
                                        (StartToken('django-variable-part'), Record(), Shift(), StopToken() )),
            State.Transition(r'\s*\}\}', (StopToken(), Shift(), Pop())),
            State.Transition(r'\s+', (Shift(), )),

            State.Transition(r'.|\s', (Error('Error in parser: django-variable'),)),
        ),
    }



class DjangoContainer(Token):
    """
    Any node which can contain both other Django nodes and DjangoContent.
    """
    pass

class DjangoContent(Token):
    """
    Any literal string to output. (html, javascript, ...)
    """
    pass


# ====================================[ Parser classes ]=====================================


class DjangoRootNode(DjangoContainer):
    """
    Root node of the parse tree.
    """
    pass

class DjangoComment(Token):
    """
    {# ... #}
    """
    def output(self, handler):
        # Don't output anything. :)
        pass

class DjangoMultilineComment(Token):
    """
    {% comment %} ... {% endcomment %}
    """
    def output(self, handler):
        # Don't output anything.
        pass

class DjangoTag(Token):
    @property
    def tagname(self):
        """
        return the tagname in: {% tagname option option|filter ... %}
        """
        # This is the first django-tag-element child
        for c in self.children:
            if c.name == 'django-tag-element':
                return c.output_as_string()

    def _args(self):
        for c in [c for c in self.children if c.name == 'django-tag-element'][1:]:
            yield c.output_as_string()

    @property
    def args(self):
        return list(self._args())

    def output(self, handler):
        handler(u'{%')
        for c in self.children:
            handler(c)
            handler(u' ')
        handler(u'%}')


class DjangoVariable(Token):
    def init_extension(self):
        self.__varname = Token.output_as_string(self, True)

    @property
    def varname(self):
        return self.__varname

    def output(self, handler):
        handler(u'{{')
        handler(self.__varname)
        handler(u'}}')


class DjangoPreprocessorConfigTag(Token):
    """
    {% ! config-option-1 cofig-option-2 %}
    """
    def process_params(self, params):
        self.preprocessor_options = [ p.output_as_string() for p in params[1:] ]

    def output(self, handler):
        # Should output nothing.
        pass

class DjangoRawOutput(Token):
    """
    {% !raw %} ... {% !endraw %}
    This section contains code which should not be validated or interpreted
    (Because is would cause trigger a false-positive "invalid HTML" or similar.)
    """
    # Note that this class does not inherit from DjangoContainer, this makes
    # sure that the html processor won't enter this class.
    def process_params(self, params):
        pass

    def output(self, handler):
        # Do not output the '{% !raw %}'-tags
        for c in self.children:
            handler(c)


class DjangoExtendsTag(Token):
    """
    {% extends varname_or_template %}
    """
    def process_params(self, params):
        param = params[1].output_as_string()

        if param[0] == '"' and param[-1] == '"':
            self.template_name = param[1:-1]
            self.template_name_is_variable = False
        elif param[0] == "'" and param[-1] == "'":
            self.template_name = param[1:-1]
            self.template_name_is_variable = False
        else:
            raise CompileException(self, 'Preprocessor does not support variable {% extends %} nodes')

            self.template_name = param
            self.template_name_is_variable = True

    def output(self, handler):
        if self.template_name_is_variable:
            handler(u'{%extends '); handler(self.template_name); handler(u'%}')
        else:
            handler(u'{%extends "'); handler(self.template_name); handler(u'"%}')


class DjangoIncludeTag(Token):
    """
    {% include varname_or_template %}
    """
    def process_params(self, params):
        param = params[1].output_as_string()

        if param[0] in ('"', "'") and param[-1] in ('"', "'"):
            self.template_name = param[1:-1]
            self.template_name_is_variable = False
        else:
            self.template_name = param
            self.template_name_is_variable = True

    def output(self, handler):
        if self.template_name_is_variable:
            handler(u'{%include '); handler(self.template_name); handler(u'%}')
        else:
            handler(u'{%include "'); handler(self.template_name); handler(u'"%}')


class DjangoDecorateTag(DjangoContainer):
    """
    {% decorate "template.html" %}
        things to place in '{{ content }}' of template.html
    {% enddecorate %}
    """
    def process_params(self, params):
        param = params[1].output_as_string()

        # Template name should not be variable
        if param[0] in ('"', "'") and param[-1] in ('"', "'"):
            self.template_name = param[1:-1]
        else:
            raise CompileException(self, 'Do not use variable template names in {% decorate %}')

    def output(self, handler):
        handler(u'{%decorate "%s" %}' % self.template_name);
        handler(self.children)
        handler(u'{%enddecorate%}')


class NoLiteraleException(Exception):
    def __init__(self):
        Exception.__init__(self, 'Not a variable')

def _variable_to_literal(variable):
    """
    if the string 'variable' represents a variable, return it
    without the surrounding quotes, otherwise raise exception.
    """
    if variable[0] in ('"', "'") and variable[-1] in ('"', "'"):
        return variable[1:-1]
    else:
        raise NoLiteraleException()


class DjangoUrlTag(DjangoTag):
    """
    {% url name param1 param2 param3=value %}
    """
    def process_params(self, params):
        self.url_params = params[1:]

    def output(self, handler):
        handler(u'{%url ')
        for c in self.url_params:
            handler(c)
            handler(u' ')
        handler(u'%}')


class DjangoTransTag(Token):
    """
    {% trans "text" %}
    """
    def process_params(self, params):
        self.__string_is_variable = False
        param = params[1].output_as_string()

        # TODO: check whether it's allowed to have variables in {% trans %},
        #       if not: cleanup code,  if allowed: support behavior in all
        #       parts of this code.
        if param[0] in ('"', "'") and param[-1] in ('"', "'"):
            self.__string = param[1:-1]
            self.__string_is_variable = False
        else:
            self.__string = param
            self.__string_is_variable = True

    @property
    def is_variable(self):
        return self.__string_is_variable

    @property
    def string(self):
        return '' if self.__string_is_variable else self.__string

    def output(self, handler):
        if self.__string_is_variable:
            handler(u'{%trans '); handler(self.__string); handler(u'%}')
        else:
            handler(u'{%trans "'); handler(self.__string); handler(u'"%}')

    @property
    def translation_info(self):
        """
        Return an object which is compatible with {% blocktrans %}-info.
        (Only to be used when this string is not a variable, so not for {% trans var %} )
        """
        class TransInfo(object):
            def __init__(self, trans):
                self.has_plural = False
                self.plural_string = u''
                self.string = trans.string
                self.variables = set()
                self.plural_variables = set()
        return TransInfo(self)

class DjangoBlocktransTag(Token):
    """
    Contains:
    {% blocktrans %} children {% endblocktrans %}
    """
    def process_params(self, params):
        # Skip django-tag-element
        self.params = params[1:]

    @property
    def is_variable(self):
        # Consider this a dynamic string (which shouldn't be translated at compile time)
        # if it has variable nodes inside. Same for {% plural %} inside the blocktrans.
        return len(list(self.child_nodes_of_class([DjangoVariable, DjangoPluralTag]))) > 0

#    @property
#    def string(self):
#        return '' if self.is_variable else self.output_as_string(True)

    @property
    def translation_info(self):
        """
        Return an {% blocktrans %}-info object which contains:
        - the string to be translated.
        - the string to be translated (in case of plural)
        - the variables to be used
        - the variables to be used (in case of plural)
        """
        convert_var = lambda v: '%%(%s)s' % v

        class BlocktransInfo(object):
            def __init__(self, blocktrans):
                # Build translatable string
                plural = False # get true when we find a plural translation
                string = []
                variables = []
                plural_string = []
                plural_variables = []

                for n in blocktrans.children:
                    if isinstance(n, DjangoPluralTag):
                        if not (len(blocktrans.params) and blocktrans.params[0].output_as_string() == 'count'):
                            raise CompileException(blocktrans,
                                    '{% plural %} tags can only appear inside {% blocktrans COUNT ... %}')
                        plural = True
                    elif isinstance(n, DjangoVariable):
                        (plural_string if plural else string).append(convert_var(n.varname))
                        (plural_variables if plural else variables).append(n.varname)
                    elif isinstance(n, DjangoContent):
                        (plural_string if plural else string).append(n.output_as_string())
                    else:
                        raise CompileException(n, 'Unexpected token in {% blocktrans %}: ' + n.output_as_string())

                # Return information
                self.has_plural = plural
                self.string = u''.join(string)
                self.plural_string = ''.join(plural_string)
                self.variables = set(variables)
                self.plural_variables = set(plural_variables)

        return BlocktransInfo(self)

    def output(self, handler):
        # Blocktrans output
        handler(u'{%blocktrans ');
        for p in self.params:
            p.output(handler)
            handler(u' ')
        handler(u'%}')
        Token.output(self, handler)
        handler(u'{%endblocktrans%}')


class DjangoPluralTag(Token):
    """
    {% plural %} tag. should only appear inside {% blocktrans %} for separating
    the singular and plural form.
    """
    def process_params(self, params):
        pass

    def output(self, handler):
        handler(u'{%plural%}')


class DjangoLoadTag(Token):
    """
    {% load module1 module2 ... %}
    """
    def process_params(self, params):
        self.modules = [ p.output_as_string() for p in params[1:] ]

    def output(self, handler):
        handler(u'{% load ')
        handler(u' '.join(self.modules))
        handler(u'%}')


class DjangoMacroTag(DjangoContainer):
    def process_params(self, params):
        assert len(params) == 2
        name = params[1].output_as_string()
        assert name[0] in ('"', "'") and name[0] == name[-1]
        self.macro_name = name[1:-1]

    def output(self, handler):
        handler(u'{%macro "'); handler(self.macro_name); handler(u'"%}')
        Token.output(self, handler)
        handler(u'{%endmacro%}')


class DjangoIfDebugTag(DjangoContainer):
    """
    {% ifdebug %} ... {% endifdebug %}
    """
    def process_params(self, params):
        pass

    def output(self, handler):
        handler(u'{%ifdebug%}')
        Token.output(self, handler)
        handler(u'{%endifdebug%}')


class DjangoCallMacroTag(Token):
    def process_params(self, params):
        assert len(params) == 2
        name = params[1].output_as_string()
        assert name[0] in ('"', "'") and name[0] == name[-1]
        self.macro_name = name[1:-1]

    def output(self, handler):
        handler(u'{%callmacro "')
        handler(self.macro_name)
        handler(u'"%}')


class DjangoCompressTag(DjangoContainer):
    """
    {% compress %} ... {% endcompress %}
    """
    def process_params(self, params):
        pass

    def output(self, handler):
        # Don't output the template tags.
        # (these are hints to the preprocessor only.)
        Token.output(self, handler)


class DjangoBlockTag(DjangoContainer):
    """
    Contains:
    {% block %} children {% endblock %}
    Note: this class should not inherit from DjangoTag, because it's .children are different...  XXX
    """
    def process_params(self, params):
        self.block_name = params[1].output_as_string()

    def output(self, handler):
        handler(u'{%block '); handler(self.block_name); handler(u'%}')
        Token.output(self, handler)
        handler(u'{%endblock%}')


# ====================================[ Parser extensions ]=====================================


# Mapping for turning the lex tree into a Django parse tree
_PARSER_MAPPING_DICT = {
    'content': DjangoContent,
    'django-tag': DjangoTag,
    'django-variable': DjangoVariable,
    'django-comment': DjangoComment,
    'django-multiline-comment': DjangoMultilineComment,
}

def _add_parser_extensions(tree):
    """
    Turn the lex tree into a parse tree.
    Actually, nothing more than replacing the parser classes, as
    a wrapper around the lex tree.
    """
    tree.__class__ = DjangoRootNode

    def _add_parser_extensions2(node):
        if isinstance(node, Token):
            if node.name in _PARSER_MAPPING_DICT:
                node.__class__ = _PARSER_MAPPING_DICT[node.name]
                if hasattr(node, 'init_extension'):
                    node.init_extension()

            for c in node.children:
                _add_parser_extensions2(c)

    _add_parser_extensions2(tree)


# Mapping for replacing the *inline* DjangoTag nodes into more specific nodes
_DJANGO_INLINE_ELEMENTS = {
    'extends': DjangoExtendsTag,
    'trans': DjangoTransTag,
    'plural': DjangoPluralTag,
    'include': DjangoIncludeTag,
    'url': DjangoUrlTag,
    'load': DjangoLoadTag,
    'callmacro': DjangoCallMacroTag,
    '!': DjangoPreprocessorConfigTag,
}

def _process_inline_tags(tree):
    """
    Replace DjangoTag elements by more specific elements.
    """
    for c in tree.children:
        if isinstance(c, DjangoTag) and c.tagname in _DJANGO_INLINE_ELEMENTS:
            # Patch class
            c.__class__ = _DJANGO_INLINE_ELEMENTS[c.tagname]

            # In-line tags don't have childnodes, but process what we had
            # as 'children' as parameters.
            c.process_params(list(c.get_childnodes_with_name('django-tag-element')))
            #c.children = [] # TODO: for Jonathan -- we want to keep this tags API compatible with the DjangoTag object, so keep children

        elif isinstance(c, DjangoTag):
            _process_inline_tags(c)


# Mapping for replacing the *block* DjangoTag nodes into more specific nodes
__DJANGO_BLOCK_ELEMENTS = {
    'block': ('endblock', DjangoBlockTag),
    'blocktrans': ('endblocktrans', DjangoBlocktransTag),
    'macro': ('endmacro', DjangoMacroTag),
    'ifdebug': ('endifdebug', DjangoIfDebugTag),
    'decorate': ('enddecorate', DjangoDecorateTag),
    'compress': ('endcompress', DjangoCompressTag),
    '!raw': ('!endraw', DjangoRawOutput),


#    'xhr': ('else', 'endxhr', DjangoXhrTag),
#    'if': ('else', 'endif', DjangoIfTag),
#    'is_enabled': ('else', 'end_isenabled', DjangoIsEnabledTag),
}




# ====================================[ Check parser settings in template {% ! ... %} ]================


def _update_preprocess_settings(tree, context):
    """
    Look for parser configuration tags in the template tree.
    Return a dictionary of the compile options to use.
    """
    for c in tree.child_nodes_of_class([ DjangoPreprocessorConfigTag ]):
        for o in c.preprocessor_options:
            context.options.change(o, c)


# ====================================[ 'Patched' class definitions ]=====================================


class DjangoPreprocessedInclude(DjangoContainer):
    def init(self, children):
        self.children = children

class DjangoPreprocessedCallMacro(DjangoContainer):
    def init(self, children):
        self.children = children

class DjangoPreprocessedUrl(DjangoContent):
    def init(self, url_value, original_urltag):
        self.children = [ url_value]
        self.original_urltag = original_urltag

class DjangoPreprocessedVariable(DjangoContent):
    def init(self, var_value):
        self.children = var_value

class DjangoTranslated(DjangoContent):
    def init(self, translated_text, translation_info):
        self.translation_info = translation_info
        self.children = [ translated_text ]



# ====================================[ Parse tree manipulations ]=====================================

def apply_method_on_parse_tree(tree, class_, method, *args, **kwargs):
    for c in tree.children:
        if isinstance(c, class_):
            getattr(c, method)(*args, **kwargs)

        if isinstance(c, Token):
            apply_method_on_parse_tree(c, class_, method, *args, **kwargs)


def _find_first_level_dependencies(tree, context):
    for node in tree.child_nodes_of_class([ DjangoIncludeTag, DjangoExtendsTag ]):
        if isinstance(node, DjangoExtendsTag):
            context.remember_extends(node.template_name)

        if isinstance(node, DjangoIncludeTag):
            context.remember_include(node.template_name)


def _process_extends(tree, context):
    """
    {% extends ... %}
    When this tree extends another template. Load the base template,
    compile it, merge the trees, and return a new tree.
    """
    extends_tag = None

    try:
        base_tree = None

        for c in tree.children:
            if isinstance(c, DjangoExtendsTag) and not c.template_name_is_variable:
                extends_tag = c
                base_tree = context.load(c.template_name)
                break

        if base_tree:
            base_tree_blocks = list(base_tree.child_nodes_of_class([ DjangoBlockTag ]))
            tree_blocks = list(tree.child_nodes_of_class([ DjangoBlockTag ]))

            # Retreive list of block tags in the outer scope of the child template.
            # These are the blocks which at least have to exist in the parent.
            outer_tree_blocks = filter(lambda b: isinstance(b, DjangoBlockTag), tree.children)

            # For every {% block %} in the base tree
            for base_block in base_tree_blocks:
                # Look for a block with the same name in the current tree
                for block in tree_blocks[:]:
                    if block.block_name == base_block.block_name:
                        # Replace {{ block.super }} variable by the parent's
                        # block node's children.
                        block_dot_super = base_block.children

                        for v in block.child_nodes_of_class([ DjangoVariable ]):
                            if v.varname == 'block.super':
                                # Found a {{ block.super }} declaration, deep copy
                                # parent nodes in here
                                v.__class__ = DjangoPreprocessedVariable
                                v.init(deepcopy(block_dot_super[:]))

                        # Replace all nodes in the base tree block, with this nodes
                        base_block.children = block.children

                        # Remove block from list
                        if block in outer_tree_blocks:
                            outer_tree_blocks.remove(block)

            # We shouldn't have any blocks left (if so, they don't have a match in the parent)
            if outer_tree_blocks:
                warning = 'Found {%% block %s %%} which has not been found in the parent' % outer_tree_blocks[0].block_name
                if context.options.disallow_orphan_blocks:
                    raise CompileException(outer_tree_blocks[0], warning)
                else:
                    context.raise_warning(outer_tree_blocks[0], warning)

            # Move every {% load %} and {% ! ... %} to the base tree
            for l in tree.child_nodes_of_class([ DjangoLoadTag, DjangoPreprocessorConfigTag ]):
                base_tree.children.insert(0, l)

            return base_tree

        else:
            return tree

    except TemplateDoesNotExist, e:
        # It is required that the base template exists.
        raise CompileException(extends_tag, 'Base template {%% extends "%s" %%} not found' %
                    (extends_tag.template_name if extends_tag else "..."))


def _preprocess_includes(tree, context):
    """
    Look for all the {% include ... %} tags and replace it by their include.
    """
    include_blocks = list(tree.child_nodes_of_class([ DjangoIncludeTag ]))

    for block in include_blocks:
        if not block.template_name_is_variable:
            try:
                # Parse include
                include_tree = context.load(block.template_name)

                # Move tree from included file into {% include %}
                block.__class__ = DjangoPreprocessedInclude
                block.init([ include_tree ])

                block.path = include_tree.path
                block.line = include_tree.line
                block.column = include_tree.column

            except TemplateDoesNotExist, e:
                raise CompileException(block, 'Template in {%% include %%} tag not found (%s)' % block.template_name)


def _preprocess_decorate_tags(tree, context):
    """
    Replace {% decorate "template.html" %}...{% enddecorate %} by the include,
    and fill in {{ content }}
    """
    class DjangoPreprocessedDecorate(DjangoContent):
        def init(self, children):
            self.children = children

    decorate_blocks = list(tree.child_nodes_of_class([ DjangoDecorateTag ]))

    for block in decorate_blocks:
        # Content nodes
        content = block.children

        # Replace content
        try:
            include_tree = context.load(block.template_name)

            for content_var in include_tree.child_nodes_of_class([ DjangoVariable ]):
                if content_var.varname == 'decorater.content':
                    content_var.__class__ = DjangoPreprocessedVariable
                    content_var.init(content)

            # Move tree
            block.__class__ = DjangoPreprocessedDecorate
            block.init([ include_tree ])

        except TemplateDoesNotExist, e:
            raise CompileException(self, 'Template in {% decorate %} tag not found (%s)' % block.template_name)


def _group_all_loads(tree):
    """
    Look for all {% load %} tags, and group them to one, on top.
    """
    all_modules = set()
    first_load_tag = None

    # Collect all {% load %} nodes.
    for load_tag in tree.child_nodes_of_class([ DjangoLoadTag ]):
        # Keeps tags like {% load ssi from future %} as they are.
        # Concatenating these is invalid.
        if not ('from' in load_tag.output_as_string()  and 'future' in load_tag.output_as_string()):
            # First tag
            if not first_load_tag:
                first_load_tag = load_tag

            for l in load_tag.modules:
                all_modules.add(l)

    # Remove all {% load %} nodes
    tree.remove_child_nodes_of_class(DjangoLoadTag)

    # Place all {% load %} in the first node of the tree
    if first_load_tag:
        first_load_tag.modules = list(all_modules)
        tree.children.insert(0, first_load_tag)

        # But {% extends %} really needs to be placed before everything else
        # NOTE: (Actually not necessary, because we don't support variable extends.)
        extends_tags = list(tree.child_nodes_of_class([ DjangoExtendsTag ]))
        tree.remove_child_nodes_of_class(DjangoExtendsTag)

        for e in extends_tags:
            tree.children.insert(0, e)

def _preprocess_urls(tree):
    """
    Replace URLs without variables by their resolved value.
    """
    # Do 'reverse' import at this point. To be sure we use the
    # latest version. Other Django plug-ins like localeurl tend
    # to monkey patch this code.
    from django.core.urlresolvers import NoReverseMatch
    from django.core.urlresolvers import reverse

    def parse_url_params(urltag):
        if not urltag.url_params:
            raise CompileException(urltag, 'Attribute missing for {% url %} tag.')

        # Parse url parameters
        name = urltag.url_params[0].output_as_string()
        args = []
        kwargs = { }
        for k in urltag.url_params[1:]:
            k = k.output_as_string()
            if '=' in k:
                k,v = k.split('=', 1)
                kwargs[str(k)] = _variable_to_literal(v)
            else:
                args.append(_variable_to_literal(k))

        return name, args, kwargs

    for urltag in tree.child_nodes_of_class([ DjangoUrlTag ]):
        try:
            name, args, kwargs = parse_url_params(urltag)
            if not 'as' in args:
                result = reverse(name, args=args, kwargs=kwargs)
                urltag_copy = deepcopy(urltag)
                urltag.__class__ = DjangoPreprocessedUrl
                urltag.init(result, urltag_copy)
        except NoReverseMatch, e:
            pass
        except NoLiteraleException, e:
            # Got some variable, can't prerender url
            pass


def _preprocess_variables(tree, values_dict):
    """
    Replace known variables, like {{ MEDIA_URL }} by their value.
    """
    for var in tree.child_nodes_of_class([ DjangoVariable ]):
        if var.varname in values_dict:
            value = values_dict[var.varname]
            var.__class__ = DjangoPreprocessedVariable
            var.init([value])

                # TODO: escape
                #       -> for now we don't escape because
                #          we are unsure of the autoescaping state.
                #          and 'resolve' is only be used for variables
                #          like MEDIA_URL which are safe in HTML.

def _preprocess_trans_tags(tree):
    """
    Replace {% trans %} and {% blocktrans %} if they don't depend on variables.
    """
    convert_var = lambda v: '%%(%s)s' % v

    for trans in tree.child_nodes_of_class([ DjangoTransTag, DjangoBlocktransTag ]):
        # Process {% blocktrans %}
        if isinstance(trans, DjangoBlocktransTag):
            translation_info = trans.translation_info

            # Translate strings
            string = _(translation_info.string)
            if translation_info.has_plural:
                plural_string = ungettext(translation_info.string, translation_info.plural_string, 2)

            # Replace %(variable)s in translated strings by {{ variable }}
            for v in translation_info.variables:
                if convert_var(v) in string:
                    string = string.replace(convert_var(v), '{{%s}}' % v)
                else:
                    raise CompileException(trans,
                            'Could not find variable "%s" in {%% blocktrans %%} "%s" after translating.' % (v, string))

            if translation_info.has_plural:
                for v in translation_info.plural_variables:
                    if convert_var(v) in plural_string:
                        plural_string = plural_string.replace(convert_var(v), '{{%s}}' % v)
                    else:
                        raise CompileException(trans,
                                'Could not find variable "%s" in {%% blocktrans %%} "%s" after translating.' % (v, plural_string))

            # Wrap in {% if test %} for plural checking and in {% with test for passing parameters %}
            if translation_info.has_plural:
                # {% blocktrans count /expression/ as /variable/ and ... %}
                output = (
                    '{%with ' + ' '.join(map(lambda t: t.output_as_string(), trans.params[1:])) + '%}' +
                    '{%if ' + trans.params[3].output_as_string() + ' > 1%}' + plural_string + '{%else%}' + string + '{%endif%}' +
                    '{%endwith%}')
            else:
                if len(trans.params):
                    # {% blocktrans with /expression/ as /variable/ and ... %}
                    output = '{%' + ' '.join(map(lambda t: t.output_as_string(), trans.params)) + '%}' + string + '{%endwith%}'
                else:
                    # {% blocktrans %}
                    output = string

            # Replace {% blocktrans %} by its translated output.
            trans.__class__ = DjangoTranslated
            trans.init(output, translation_info)

        # Process {% trans "..." %}
        else:
            if not trans.is_variable:
                output = _(trans.string)
                translation_info = trans.translation_info
                trans.__class__ = DjangoTranslated
                trans.init(output, translation_info)


def _preprocess_ifdebug(tree):
    if settings.DEBUG:
        for ifdebug in tree.child_nodes_of_class([ DjangoIfDebugTag ]):
            tree.replace_child_by_nodes(ifdebug, ifdebug.children)
    else:
        tree.remove_child_nodes_of_class(DjangoIfDebugTag)


def _preprocess_macros(tree):
    """
    Replace every {% callmacro "name" %} by the content of {% macro "name" %} ... {% endmacro %}
    NOTE: this will not work with recursive macro calls.
    """
    macros = { }
    for m in tree.child_nodes_of_class([ DjangoMacroTag ]):
        macros[m.macro_name] = m

    for call in tree.child_nodes_of_class([ DjangoCallMacroTag ]):
        if call.macro_name in macros:
            # Replace the call node by a deep-copy of the macro childnodes
            call.__class__ = DjangoPreprocessedCallMacro
            call.init(deepcopy(macros[call.macro_name].children[:]))

    # Remove all macro nodes
    tree.remove_child_nodes_of_class(DjangoMacroTag)


def _execute_preprocessable_tags(tree):
    preprocessable_tags = get_preprocessable_tags()

    for c in tree.children:
        if isinstance(c, DjangoTag) and c.tagname in preprocessable_tags:
            params = [ p.output_as_string() for p in c.get_childnodes_with_name('django-tag-element') ]
            try:
                c.children = [ preprocessable_tags[c.tagname](*params) ]
                c.__class__ = DjangoContent
            except NotPreprocessable:
                pass

        elif isinstance(c, DjangoContainer):
            _execute_preprocessable_tags(c)


def remember_gettext_entries(tree, context):
    """
    Look far all the {% trans %} and {% blocktrans %} tags in the tree,
    and copy the translatable strings into the context.
    """
    # {% trans %}
    for node in tree.child_nodes_of_class([ DjangoTransTag]):
        context.remember_gettext(node, node.string)

    # {% blocktrans %}
    for node in tree.child_nodes_of_class([ DjangoBlocktransTag]):
        info = node.translation_info

        context.remember_gettext(node, info.string)

        if info.has_plural:
            context.remember_gettext(node, info.plural_string)



from template_preprocessor.core.html_processor import compile_html


def parse(source_code, path, context, main_template=False):
    """
    Parse the code.
    - source_code: string
    - path: for attaching meta information to the tree.
    - context: preprocess context (holding the settings/dependecies/warnings, ...)
    - main_template: False for includes/extended templates. True for the
                     original path that was called.
    """
    # To start, create the root node of a tree.
    tree = Token(name='root', line=1, column=1, path=path)
    tree.children = [ source_code ]

    # Lex Django tags
    tokenize(tree, __DJANGO_STATES, [Token])

    # Phase I: add parser extensions
    _add_parser_extensions(tree)

    # Phase II: process inline tags
    _process_inline_tags(tree)

    # Phase III: create recursive structure for block level tags.
    nest_block_level_elements(tree, __DJANGO_BLOCK_ELEMENTS, [DjangoTag], lambda c: c.tagname)

    # === Actions ===

    if main_template:
        _find_first_level_dependencies(tree, context)

    # Extend parent template and process includes
    tree = _process_extends(tree, context) # NOTE: this returns a new tree!
    _preprocess_includes(tree, context)
    _preprocess_decorate_tags(tree, context)

    # Following actions only need to be applied if this is the 'main' tree.
    # It does not make sense to apply it on every include, and then again
    # on the complete tree.
    if main_template:
        _update_preprocess_settings(tree, context)
        options = context.options

        # Remember translations in context (form PO-file generation)
        remember_gettext_entries(tree, context)

        # Do translations
        if options.preprocess_translations:
            _preprocess_trans_tags(tree)

        # Reverse URLS
        if options.preprocess_urls:
            _preprocess_urls(tree)

        # Do variable lookups
        if options.preprocess_variables:
            sites_enabled = 'django.contrib.sites' in settings.INSTALLED_APPS

            _preprocess_variables(tree,
                        {
                            'MEDIA_URL': getattr(settings, 'MEDIA_URL', ''),
                            'STATIC_URL': getattr(settings, 'STATIC_URL', ''),
                        })
            if sites_enabled:
                from django.contrib.sites.models import Site
                _preprocess_variables(tree,
                        {
                            'SITE_DOMAIN': Site.objects.get_current().domain,
                            'SITE_NAME': Site.objects.get_current().name,
                            'SITE_URL': 'http://%s' % Site.objects.get_current().domain,
                        })

        # Don't output {% block %} tags in the compiled file.
        if options.remove_block_tags:
            tree.collapse_nodes_of_class(DjangoBlockTag)

        # Preprocess {% callmacro %} tags
        if options.preprocess_macros:
            _preprocess_macros(tree)

        if options.preprocess_ifdebug:
            _preprocess_ifdebug(tree)

        # Group all {% load %} statements
        if options.merge_all_load_tags:
            _group_all_loads(tree)

        # Preprocessable tags
        if options.execute_preprocessable_tags:
            _execute_preprocessable_tags(tree)

        # HTML compiler
        if options.is_html:
            compile_html(tree, context)

    return tree
