#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Django template preprocessor.
Author: Jonathan Slenders, City Live
"""


"""
Javascript parser for the template preprocessor.
-----------------------------------------------

Compile the javascript code inside the parse tree
of django template nodes.
"""


# =========================[ Javascript Lexer ]===========================

from template_preprocessor.core.django_processor import DjangoContent, DjangoContainer, DjangoTag
from template_preprocessor.core.lexer import State, StartToken, Push, Record, Shift, StopToken, Pop, CompileException, Token, Error
from template_preprocessor.core.lexer_engine import tokenize
from template_preprocessor.core.html_processor import HtmlContent
import string
from django.utils.translation import ugettext as _

__JS_KEYWORDS = 'break|catch|const|continue|debugger|default|delete|do|else|enum|false|finally|for|function|gcase|if|in|instanceof|new|null|return|switch|this|throw|true|try|typeof|var|void|while|with'.split('|')


__JS_STATES = {
    'root' : State(
            State.Transition(r'\s*\{\s*', (StartToken('js-scope'), Shift(), )),
            State.Transition(r'\s*\}\s*', (StopToken('js-scope'), Shift(), )),
            State.Transition(r'/\*', (Push('multiline-comment'), Shift(), )),
            State.Transition(r'//', (Push('singleline-comment'), Shift(), )),
            State.Transition(r'"', (Push('double-quoted-string'), StartToken('js-double-quoted-string'), Shift(), )),
            State.Transition(r"'", (Push('single-quoted-string'), StartToken('js-single-quoted-string'), Shift(), )),

            State.Transition(r'(break|catch|const|continue|debugger|default|delete|do|else|enum|false|finally|for|function|case|if|in|instanceof|new|null|return|switch|this|throw|true|try|typeof|var|void|while|with)(?![a-zA-Z0-9_$])',
                                    (StartToken('js-keyword'), Record(), Shift(), StopToken())),

                # Whitespaces are recorded in the operator. (They can be removed later on by a simple trim operator.)
            State.Transition(r'\s*([;,=?:|^&=!<>*%~\.+-])\s*', (StartToken('js-operator'), Record(), Shift(), StopToken(), )),

                # Place ( ... ) and [ ... ] in separate nodes.
                # After closing parentheses/square brakets. Go 'after-varname' (because the context is the same.)
            State.Transition(r'\s*(\()\s*', (StartToken('js-parentheses'), Shift(), )),
            State.Transition(r'\s*(\))\s*', (StopToken('js-parentheses'), Shift(), Push('after-varname'), )),
            State.Transition(r'\s*(\[)\s*', (StartToken('js-square-brackets'), Shift(), )),
            State.Transition(r'\s*(\])\s*', (StopToken('js-square-brackets'), Shift(), Push('after-varname'), )),

                # Varnames and numbers
            State.Transition(r'[a-zA-Z_$][a-zA-Z_$0-9]*', (StartToken('js-varname'), Record(), Shift(), StopToken(), Push('after-varname') )),
            State.Transition(r'[0-9.]+', (StartToken('js-number'), Record(), Shift(), StopToken(), Push('after-varname') )),

                # Required whitespace here (to be replaced with at least a space.)
            State.Transition(r'\s+', (StartToken('js-whitespace'), Record(), Shift(), StopToken() )), # Skip whitespace.

                # A slash in here means we are at the start of a regex block.
            State.Transition(r'\s*/(?![/*])', (StartToken('js-regex-object'), Record(), Shift(), Push('regex-object') )),

            State.Transition(r'.|\s', (Error('Error in parser #1'),)),
            ),
    'double-quoted-string': State(
            State.Transition(r'"', (Pop(), Shift(), StopToken(), )),
            State.Transition(r"\\'", (Record("'"), Shift(), )),
            State.Transition(r'\\.', (Record(), Shift(), )),
            State.Transition(r'[^"\\]+', (Record(), Shift(), )),
            State.Transition(r'.|\s', (Error('Error in parser #2'),)),
            ),
    'single-quoted-string': State(
            State.Transition(r"'", (Pop(), Shift(), StopToken(), )),
            State.Transition(r'\\"', (Record('"'), Shift(), )),
            State.Transition(r'\\.', (Record(), Shift() )),
            State.Transition(r"[^'\\]+", (Record(), Shift(), )),
            State.Transition(r'.|\s', (Error('Error in parser #3'),)),
            ),

    'multiline-comment': State(
            State.Transition(r'\*/', (Shift(), Pop(), )), # End comment
            State.Transition(r'(\*(?!/)|[^\*])+', (Shift(), )), # star, not followed by slash, or non star characters
            State.Transition(r'(\*(?!/))+', (Shift(), )), # star, not followed by slash
            State.Transition(r'.|\s', (Error('Error in parser #4'),)),
            ),

    'singleline-comment': State(
            State.Transition(r'\n', (Shift(), Pop(), )), # End of line is end of comment
            State.Transition(r'[^\n]+', (Shift(), )),
            State.Transition(r'.|\s', (Error('Error in parser #5'),)),
            ),

    'after-varname': State(
            # A slash after a varname means we have a division operator.
            State.Transition(r'\s*/(?![/*])\s*', (StartToken('js-operator'), Record(), Shift(), StopToken(), )),

            State.Transition(r'/\*', (Push('multiline-comment'), Shift(), )),
            State.Transition(r'//[^\n]*', (Shift(), )), # Single line comment

            # None of the previous matches? Pop and get again in the root state
            State.Transition(r'.|\s', (Pop(), )),
            State.Transition(r'.|\s', (Error('Error in parser #6'),)),
            ),

    'regex-object': State(
            State.Transition(r'\\.', (Record(), Shift() )),
            State.Transition(r'[^/\\]+', (Record(), Shift(), )),
            State.Transition(r'/[a-z]?', (Record(), Shift(), StopToken(), Pop() )), # End of regex object
            State.Transition(r'.|\s', (Error('Error in parser #7'),)),
            ),
   }



# =========================[ Javascript Parser ]===========================

class JavascriptNode(HtmlContent):
    pass


class JavascriptScope(JavascriptNode):
    """
    Contains:
    Something between { curly brackets } in javascript.
    """
    def init_extension(self):
        self.symbol_table = { }

    def output(self, handler):
        handler(u'{')
        Token.output(self, handler)
        handler(u'}')


class JavascriptParentheses(JavascriptNode):
    """
    Contains:
    Something between ( parentheses ) in javascript.
    """
    def output(self, handler):
        handler(u'(')
        Token.output(self, handler)
        handler(u')')


class JavascriptSquareBrackets(JavascriptNode):
    """
    Contains:
    Something between ( parentheses ) in javascript.
    """
    def output(self, handler):
        handler(u'[')
        Token.output(self, handler)
        handler(u']')


class JavascriptWhiteSpace(JavascriptNode):
    pass


class JavascriptOperator(JavascriptNode):
    """
    Javascript operator.
    """
    @property
    def operator(self):
        return self.output_as_string().strip()

    @property
    def is_comma(self):
        return self.operator == ','

    @property
    def is_semicolon(self):
        return self.operator == ';'

    @property
    def is_colon(self):
        return self.operator == ':'


class JavascriptKeyword(JavascriptNode):
    """
    Any javascript keyword: like 'function' or 'var'...
    """
    @property
    def keyword(self):
        return self.output_as_string()


class JavascriptVariable(JavascriptNode):
    """
    Any javascript variable:
    """
    def init_extension(self):
        self.__varname = None
        self.__link_to = None

    def link_to_variable(self, variable):
        self.__link_to = variable

    def has_been_linked(self):
        return bool(self.__link_to)

    @property
    def varname(self):
        return self.output_as_string()

    @varname.setter
    def varname(self, varname):
        self.__varname = varname

    def output(self, handler):
        # Yield this node's content, or if the variable name
        # has been changed, use the modified name.
        if self.__varname:
            handler(self.__varname)

        elif self.__link_to:
            self.__link_to.output(handler)

        else:
            Token.output(self, handler)

class JavascriptString(JavascriptNode):
    @property
    def value(self):
        """
        String value. Has still escaped special characters,
        but no escapes for quotes.
        """
        return self.output_as_string(use_original_output_method=True)

    def output(self, handler):
        raise Exception("Don't call output on abstract base class")

class JavascriptDoubleQuotedString(JavascriptString):
    def output(self, handler):
        handler(u'"')
        handler(self.value.replace('"', r'\"'))
        handler(u'"')


class JavascriptSingleQuotedString(JavascriptString):
    def output(self, handler):
        handler(u"'")
        handler(self.value.replace("'", r"\'"))
        handler(u"'")


class JavascriptRegexObject(JavascriptNode):
    pass

class JavascriptNumber(JavascriptNode):
    pass

__JS_EXTENSION_MAPPINGS = {
        'js-scope': JavascriptScope,
        'js-parentheses': JavascriptParentheses,
        'js-square-brackets': JavascriptSquareBrackets,
        'js-varname': JavascriptVariable,
        'js-keyword': JavascriptKeyword,
        'js-whitespace': JavascriptWhiteSpace,
        'js-operator': JavascriptOperator,
        'js-double-quoted-string': JavascriptDoubleQuotedString,
        'js-single-quoted-string': JavascriptSingleQuotedString,
        'js-regex-object': JavascriptRegexObject,
        'js-number': JavascriptNumber,
}


def _add_javascript_parser_extensions(js_node):
    """
    Patch (some) nodes in the parse tree, to get the JS parser functionality.
    """
    js_node.symbol_table = { }

    for c in js_node.children:
        if isinstance(c, Token):
            # Patch the js scope class
            if c.name in __JS_EXTENSION_MAPPINGS:
                c.__class__ = __JS_EXTENSION_MAPPINGS[c.name]
                if hasattr(c, 'init_extension'):
                    c.init_extension()

            _add_javascript_parser_extensions(c)


# =========================[ Javascript processor ]===========================


def _compress_javascript_whitespace(js_node, root_node=True):
    """
    Remove all whitepace in javascript code where possible.
    """
    for c in js_node.children:
        if isinstance(c, Token):
            # Whitespcae tokens are required to be kept. e.g. between 'var' and the actual varname.
            if isinstance(c, JavascriptWhiteSpace):
                c.children = [u' ']

            # Around operators, we can delete all whitespace.
            if isinstance(c, JavascriptOperator):
                c.children = [ c.operator ]

            _compress_javascript_whitespace(c, root_node=False)

    # In the root node, we can remove all leading and trailing whitespace
    if len(js_node.children):
        for i in (0, -1):
            if isinstance(js_node.children[i], JavascriptWhiteSpace):
               js_node.children[i].children = [ u'' ]


def _minify_variable_names(js_node):
    """
    Look for all variables in the javascript code, and
    replace it with a name, as short as possible.
    """
    global_variable_names = []

    # Walk through all the JavascriptScope elements in the tree.
    # Detect variable declaration (variables preceded by a 'function' or 'var'
    # keyword.  Save in the scope that it declares a variable with that name.
    # (do this recursively for every javascript scope.)
    def find_variables(js_node, scope, in_root_node=True):
        next_is_variable = False
        for index, c in enumerate(js_node.children):
            # Look for 'function' and 'var'
            if isinstance(c, JavascriptKeyword) and c.keyword in ('function', 'var') and not in_root_node:
                next_is_variable = True

                # NOTE: the `in_root_node` check is required because "var
                # varname" should not be renamed, if it's been declared in the
                # global scope. We only want to rename variables in private
                # nested scopes.

                if c.keyword == 'function':
                    find_variables_in_function_parameter_list(js_node.children[index:])

            elif isinstance(c, JavascriptVariable) and next_is_variable:
                scope.symbol_table[c.varname] = c
                next_is_variable = False

            elif isinstance(c, JavascriptScope):
                find_variables(c, c, False)
                next_is_variable = False

            elif isinstance(c, JavascriptWhiteSpace):
                pass

            elif isinstance(c, JavascriptParentheses) or isinstance(c, JavascriptSquareBrackets):
                find_variables(c, scope)
                next_is_variable = False

            elif isinstance(c, Token):
                find_variables(c, scope)
                next_is_variable = False

            else:
                next_is_variable = False


    # Detect variable declarations in function parameters
    # In the following example are 'varname1' and 'varname2' variable declarations
    # in the scope between the curly brackets.
    # function(varname1, varname2, ...)  {   ... }
    def find_variables_in_function_parameter_list(nodelist):
        # The `nodelist` parameter is the nodelist of the parent parsenode, starting with the 'function' keyword
        assert isinstance(nodelist[0], JavascriptKeyword) and nodelist[0].keyword == 'function'
        i = 1

        while isinstance(nodelist[i], JavascriptWhiteSpace):
            i += 1

        # Skip function name (and optional whitespace after function name)
        if isinstance(nodelist[i], JavascriptVariable):
            i += 1
            while isinstance(nodelist[i], JavascriptWhiteSpace):
                i += 1

        # Enter function parameter list
        if isinstance(nodelist[i], JavascriptParentheses):
            # Remember function parameters
            variables = []
            need_comma = False # comma is the param separator
            for n in nodelist[i].children:
                if isinstance(n, JavascriptWhiteSpace):
                    pass
                elif isinstance(n, JavascriptVariable):
                    variables.append(n)
                    need_comma = True
                elif isinstance(n, JavascriptOperator) and n.is_comma and need_comma:
                    need_comma = False
                else:
                    raise CompileException(node, 'Unexpected token in function parameter list')

            # Skip whitespace after parameter list
            i += 1
            while isinstance(nodelist[i], JavascriptWhiteSpace):
                i += 1

            # Following should be a '{', and bind found variables to scope
            if isinstance(nodelist[i], JavascriptScope):
                for v in variables:
                    nodelist[i].symbol_table[v.varname] = v
            else:
                raise CompileException(nodelist[i], 'Expected "{" after function definition')
        else:
            raise CompileException(nodelist[i], 'Expected "(" after function keyword')

    find_variables(js_node, js_node)


    # Walk again through the tree. For all the variables: look in the parent
    # scopes where is has been defined. If it's never been defined, add it to
    # the global variable names. (names that we should avoid other variables to
    # be renamed to.) If it has been defined in a parent scope, link it to that
    # variable in that scope.
    def find_free_variables(js_node, parent_scopes):
        skip_next_var = False

        for index, c in enumerate(js_node.children):
            # Variables after a dot operator shouldn't be renamed.
            if isinstance(c, JavascriptOperator):
                skip_next_var = (c.operator == '.')

            elif isinstance(c, JavascriptVariable):
                # Test whether this is not the key of a dictionary,
                # if so, we shouldn't rename it.
                try:
                    n = js_node.children[index+1]
                    if isinstance(n, JavascriptOperator) and n.is_colon:
                        skip_next_var = True
                except IndexError, e:
                    pass

                # If we have to link this var (not after a dot, not before a colon)
                if not skip_next_var:
                    # Link variable to definition symbol table
                    varname = c.varname
                    linked = False
                    for s in parent_scopes:
                        if varname in s.symbol_table:
                            c.link_to_variable(s.symbol_table[varname])
                            linked = True
                            break

                    if not linked:
                        global_variable_names.append(varname)

            elif isinstance(c, JavascriptScope):
                find_free_variables(c, [c] + parent_scopes)

            elif isinstance(c, Token):
                find_free_variables(c, parent_scopes)

    find_free_variables(js_node, [ js_node ])

    # Following is a helper method for generating variable names
    def generate_varname(avoid_names):
        avoid_names += __JS_KEYWORDS
        def output(c):
            return ''.join([ string.lowercase[i] for i in c ])

        c = [0] # Numeral representation of character array
        while output(c) in avoid_names:
            c[0] += 1

            # Overflow dectection
            for i in range(0, len(c)):
                if c[i] == 26: # Overflow
                    c[i] = 0
                    try:
                        c[i+1] += 1
                    except IndexError:
                        c.append(0)

        return output(c)

    # Now, rename all the local variables. Start from the outer scope, and move to the
    # inner scopes. Use the first free variable name. Pass each time to the inner scopes,
    # which variables that shouldn't be used. (However, they can be redeclared again, if they
    # are not needed in the inner scope.)
    def rename_variables(js_node, avoid_names):
        if hasattr(js_node, 'symbol_table'):
            for s in js_node.symbol_table:
                new_name = generate_varname(avoid_names)
                avoid_names = avoid_names + [ new_name ]
                js_node.symbol_table[s].varname = new_name

        for c in js_node.children:
            if isinstance(c, Token):
                rename_variables(c, avoid_names[:])

    rename_variables(js_node, global_variable_names[:])


def fix_whitespace_bug(js_node):
    """
    Fixes the following case in js code:
        <script type="text/javascript"> if {  {% if test %} ... {% endif %} } </script>
    The lexer above would remove the space between the first '{' and '{%'. This collision
    would make Django think it's the start of a variable.
    """
    # For every scope (starting with '{')
    for scope in js_node.child_nodes_of_class([JavascriptScope]):
        # Look if the first child inside this scope also renders to a '{'
        if scope.children and scope.children[0].output_as_string()[0:1] == '{':
            # If so, insert a whitespace token in between.
            space = Token(name='required-whitespace')
            space.children = [' ']
            scope.children.insert(0, space)


def _validate_javascript(js_node):
    # Check whether no comma appears at the end of any scope.
    # e.g.    var x = { y: z, } // causes problems in IE6 and IE7
    for scope in js_node.child_nodes_of_class([JavascriptScope]):
        if scope.children:
            last_child = scope.children[-1]
            if isinstance(last_child, JavascriptOperator) and last_child.is_comma:
                raise CompileException(last_child,
                            'Please remove colon at the end of Javascript object (not supported by IE6 and IE7)')

    # Check whether no semi-colons are missing. Javascript has optional
    # semicolons and uses an insertion mechanism, but it's very bad to rely on
    # this. If semicolons are missing, we consider the code invalid.  Every
    # statement should end with a semi colon, except: for, function, if,
    # switch, try and while (See JSlint.com)
    for scope in js_node.child_nodes_of_class([JavascriptScope]):
        i = [0] # Variable by referece

        def next():
            i[0] += 1

        def current_node():
            return scope.children[i[0]]

        def get_last_non_whitespace_token():
            if i[0] > 0:
                j = i[0] - 1
                while j > 0 and isinstance(scope.children[j], JavascriptWhiteSpace):
                        j -= 1
                if j:
                    return scope.children[j]

        def found_missing():
            raise CompileException(current_node(), 'Missing semicolon detected. Please check your Javascript code.')

        semi_colon_required = False

        while i[0] < len(scope.children):
            c = current_node()

            if isinstance(c, JavascriptKeyword) and c.keyword in ('for', 'if', 'switch', 'function', 'try', 'catch', 'while'):
                if (semi_colon_required):
                    found_missing()

                semi_colon_required = False

                if c.keyword == 'function':
                    # One *exception*: When this is an function-assignment, a
                    # semi-colon IS required after this statement.
                    last_token = get_last_non_whitespace_token()
                    if isinstance(last_token, JavascriptOperator) and last_token.operator == '=':
                        semi_colon_required = True

                    # Skip keyword
                    next()

                    # and optional also function name
                    while isinstance(current_node(), JavascriptWhiteSpace):
                        next()
                    if isinstance(current_node(), JavascriptVariable):
                        next()
                else:
                    # Skip keyword
                    next()

                # Skip whitespace
                while isinstance(current_node(), JavascriptWhiteSpace):
                    next()

                # Skip over the  '(...)' parameter list
                # Some blocks, like try {}  don't have parameters.
                if isinstance(current_node(), JavascriptParentheses):
                    next()

                # Skip whitespace
                while isinstance(current_node(), JavascriptWhiteSpace):
                    next()

                # Skip scope { ... }
                if isinstance(current_node(), JavascriptScope):
                    next()

                i[0] -= 1

            elif isinstance(c, JavascriptKeyword) and c.keyword == 'var':
                # The previous token, before the 'var' keyword should be semi-colon
                last_token = get_last_non_whitespace_token()
                if last_token:
                    if isinstance(last_token, JavascriptOperator) and last_token.operator == ';':
                        pass
                    elif isinstance(last_token, JavascriptScope) or isinstance(last_token, DjangoTag):
                        pass
                    else:
                        found_missing()

            elif isinstance(c, JavascriptOperator):
                # Colons, semicolons, ...
                # No semicolon required before or after
                semi_colon_required = False

            elif isinstance(c, JavascriptParentheses) or isinstance(c, JavascriptSquareBrackets):
                semi_colon_required = True

            elif isinstance(c, JavascriptScope):
                semi_colon_required = False

            elif isinstance(c, JavascriptVariable):
                if (semi_colon_required):
                    found_missing()

                semi_colon_required = True

            elif isinstance(c, JavascriptWhiteSpace):
                # Skip whitespace
                pass

            next()


def _process_gettext(js_node, validate_only=False):
    """
    Validate whether gettext(...) function in javascript get a string as
    parameter. (Or concatenation of several strings)
    """
    for scope in js_node.child_nodes_of_class([JavascriptScope, JavascriptSquareBrackets, JavascriptParentheses]):
        nodes = scope.children
        for i, c in enumerate(nodes):
            # Is this a gettext method?
            if isinstance(nodes[i], JavascriptVariable) and nodes[i].varname == 'gettext':
                try:
                    gettext = nodes[i]

                    # Test '('
                    i += 1
                    while isinstance(nodes[i], JavascriptWhiteSpace):
                        i += 1

                    # When gettext is followed by '()', this is a call to gettext, otherwise, gettext is used
                    # as a variable.
                    if isinstance(nodes[i], JavascriptParentheses):
                        parentheses = nodes[i]

                        # Read content of gettext call.
                        body = []
                        for node in parentheses.children:
                            if isinstance(node, JavascriptOperator) and node.operator == '+':
                                # Skip concatenation operator
                                pass
                            elif isinstance(node, JavascriptString):
                                body.append(node.value)
                            else:
                                raise CompileException(node, 'Unexpected token inside gettext(...)')

                        if not validate_only:
                            # Translate content
                            translation = _(u''.join(body))

                            # Replace gettext(...) call by its translation (in double quotes.)
                            gettext.__class__ = JavascriptDoubleQuotedString
                            gettext.children = [ translation.replace('"', r'\"') ]
                            nodes.remove(parentheses)
                except IndexError, i:
                    # i got out of the nodes array
                    pass


def compile_javascript(js_node):
    """
    Compile the javascript nodes to more compact code.
    - Remove comments
    - Rename private variables.
    - Remove whitespace.

    js_node is a node in the parse tree. Note that it may contain
    template tag nodes, and that we should also parse through the block
    nodes.
    """
    # Tokenize and compile
    tokenize(js_node, __JS_STATES, [HtmlContent], [DjangoContainer])
    _compile(js_node)


def compile_javascript_string(js_string, path=''):
    """
    Compile JS code (can be used for external javascript files)
    """
    # First, create a tree to begin with
    tree = Token(name='root', line=1, column=1, path=path)
    tree.children = [ js_string ]

    # Tokenize
    tokenize(tree, __JS_STATES, [Token] )

    # Compile
    _compile(tree)

    # Output
    return tree.output_as_string()


def _compile(js_node):
    # Javascript parser extensions (required for proper output)
    _add_javascript_parser_extensions(js_node)

    # Validate javascript
    _validate_javascript(js_node)

    # Remove meaningless whitespace in javascript code.
    _compress_javascript_whitespace(js_node)

    # Preprocess gettext
    _process_gettext(js_node)

    # Minify variable names
    _minify_variable_names(js_node)

    fix_whitespace_bug(js_node)


