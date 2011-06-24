# Author: Jonathan Slenders, City Live

#
#  !!!! THIS IS AN *EXPERIMENTAL* COMPILED RENDER ENGINE FOR DJANGO TEMPLATES
#  !!!!      -- NOT READY FOR PRODUCTION --
#


# Only some ideas and pseudo code for implementing a faster template rendering
# engine. The idea is to totally replace Django's engine, by writing a new
# rendering engine compatible with Django's 'Template'-object.

# It should be a two-step rendering engine
# 1. Preprocess template to a the new, more compact version which is still
#    compatible with Django. (with the preprocessor as we now do.) 2.
# 2. Generate Python code from each Template. (Template tags are not
#    compatible, because they literrally plug into the current Django parser,
#    but template filters are reusable.) Call 'compile' on the generated code,
#    wrap in into a Template-compatible object and return from the template loader.



# Some tricks we are going to use:
# 1. Compiled code will use local variables where possible. Following translations will be made:
#         {{ a }}   ->    a
#         {{ a.b }}   ->    a.b
#         {{ a.0.c }}   ->    a[0].c
#         {{ a.get_profile.c }}   ->  a.get_profile.c  # proxy of get_profile will call itself when resolving c.
#
#    Accessing local variables should be extremely fast in python, if a
#    variable does not exist in the locals(), python will automatically look
#    into the globals. But if we run this code through an eval() call, it is
#    possible to pass our own Global class which will transparantly redirect
#    lookups to the context if they were not yet assigned by generated code.
#    http://stackoverflow.com/questions/3055228/how-to-override-built-in-getattr-in-python
#
#

# 2. Generated code will output by using 'print', not yield. We will replace
#    sys.stdout for capturing render output and ''.join -it afterwards. To
#    restore: sys.stdout=sys.__stdout__
#    -> UPDATE: it's difficult to replace stdout. it would cause difficult template
#    tag implementations, when using tags like {% filter escape %}i[Madi, it would cause
#    several levels of wrapped-stdouts. -> now using a custom _write function.


# Very interesting documentation:
# http://docs.python.org/reference/executionmodel.html


from template_preprocessor.core.django_processor import DjangoTag, DjangoContent, DjangoVariable, DjangoPreprocessorConfigTag, DjangoTransTag, DjangoBlocktransTag, DjangoComment, DjangoMultilineComment, DjangoUrlTag, DjangoLoadTag, DjangoCompressTag, DjangoRawOutput
from template_preprocessor.core.html_processor import HtmlNode
from django.utils.translation import ugettext as _

from template_preprocessor.core.lexer import Token, State, StartToken, Shift, StopToken, Push, Pop, Error, Record, CompileException
from template_preprocessor.core.lexer_engine import tokenize

from template_preprocessor.core.lexer import CompileException

import sys

def _escape_python_string(string):
    return string.replace('"', r'\"')



# States for django variables

        # Grammar rules:
        # [ digits | quoted_string | varname ]
        # ( "." [ digits | quoted_string | varname ]) *
        # ( "|" filter_name ":" ? quoted_string "?" ) *


_DJANGO_VARIABLE_STATES = {
    'root' : State(
            State.Transition(r'_\(', (StartToken('trans'), Shift(), )),
            State.Transition(r'\)', (StopToken('trans'), Shift(), )),

            # Start of variable
            State.Transition(r'[0-9]+', (StartToken('digits'), Record(), Shift(), StopToken(), )),
            State.Transition(r'[a-zA-Z][0-9a-zA-Z_]*', (StartToken('name'), Record(), Shift(), StopToken(), )),
            State.Transition(r'"[^"]*"', (StartToken('string'), Record(), Shift(), StopToken(), )),
            State.Transition(r"'[^']*'", (StartToken('string'), Record(), Shift(), StopToken(), )),
            State.Transition(r'\.', (StartToken('dot'), Record(), Shift(), StopToken(), )),
            State.Transition(r'\|', (StartToken('pipe'), Record(), Shift(), StopToken(), )),
            State.Transition(r':', (StartToken('filter-option'), Record(), Shift(), StopToken() )),

            State.Transition(r'.|\s', (Error('Not a valid variable'),)),
            ),
}



# ==================================[ Code generator ]===================================


class CodeGenerator(object):
    """
    Object where the python output code will we placed into. It contains some
    utilities for tracking which variables in Python are already in use.
    """
    def __init__(self):
        self._code = [] # Lines of code, terminating \n not required after each line.
        self._tmp_print_code = [] # Needed to group print consecutive statements
        self._indent_level = 0

        # Push/pop stack of variable scopes.
        self._scopes = [ set() ]

        self._tag = None

    def tag_proxy(self, tag):
        """
        Return interface to this code generator, where every call is supposed to
        be executed on this tag (=parse token).
        (This does avoid the need of having to pass the tag to all the template
        tag implementations, and makes 'register_variable' aware of the current
        tag, so that proper exeptions with line numbers can be thrown.)
        """
        class CodeGeneratorProxy(object):
            def __getattr__(s, attr):
                self._tag = tag
                return getattr(self, attr)

            @property
            def current_tag(self):
                return self._tag
        return CodeGeneratorProxy()

    def write(self, line, _flush=True):
        if _flush:
            self._flush_print_cache()
        self._code.append('\t'*self._indent_level + line)

    def _flush_print_cache(self):
        if self._tmp_print_code:
            self.write('_w(u"""%s""")' % _escape_python_string(''.join(self._tmp_print_code)), False)
            self._tmp_print_code = []

    def write_print(self, text):
        if text:
            self._tmp_print_code.append(text)

    def indent(self):
        """
        Indent source code written in here. (Nested in current indentation level.)
        Usage: with generator.indent():
        """
        class Indenter(object):
            def __enter__(s):
                self._flush_print_cache()
                self._indent_level += 1

            def __exit__(s, type, value, traceback):
                self._flush_print_cache()
                self._indent_level -= 1
        return Indenter()

    def write_indented(self, lines):
        with self.indent():
            for l in lines:
                self.write(l)

    def register_variable(self, var):
        #if self.variable_in_current_scope(var):
        if var in self._scopes[-1]:
            raise CompileException(self._tag, 'Variable "%s" already defined in current scope' % var)
        else:
            self._scopes[-1].add(var)


    def scope(self):
        """
        Enter a new scope. (Nested in current scope.)
        Usage: with generator.scope():
        """
        class ScopeCreater(object):
            def __enter__(s):
                self._scopes.append(set())

            def __exit__(s, type, value, traceback):
                self._scopes.pop()
        return ScopeCreater()

    def variable_in_current_scope(self, variable):
        """
        True when this variable name has been defined in the current or one of the
        parent scopes.
        """
        return any(map(lambda scope: variable in scope, self._scopes))

    def convert_variable(self, name):
        """
        Convert a template variable to a Python variable.
        """
        # 88 -> 88
        # a.1.b -> a[1].b
        # 8.a   -> CompileException
        # "..." -> "..."
        # var|filter:"..."|filter2:value  -> _filters['filter2'](_filters['filter'](var))

        # Parse the variable
        tree = Token(name='root', line=1, column=1, path='django variable')
        tree.children = [ name ]
        tokenize(tree, _DJANGO_VARIABLE_STATES, [Token])

        #print tree._print()

        def handle_filter(subject, children):
            filter_name = None
            filter_option = None
            in_filter_option = False

            def result():
                assert filter_name

                if filter_name in _native_filters:
                    return _native_filters[filter_name](self, subject, filter_option)

                elif filter_option:
                    return '_f["%s"](%s, %s)' % (filter_name, subject, filter_option)

                else:
                    return '_f["%s"](%s)' % (filter_name, subject)

            for i in range(0,len(children)):
                part = children[i].output_as_string()
                c = children[i]

                if c.name == 'digits':
                    if not filter_option and in_filter_option:
                        filter_option = part
                    else:
                        raise CompileException(self._tag, 'Invalid variable')

                elif c.name == 'name':
                    if not filter_option and in_filter_option:
                        filter_option = part

                    elif not filter_name:
                        filter_name = part
                    else:
                        raise CompileException(self._tag, 'Invalid variable')

                elif c.name == 'string':
                    if not filter_option and in_filter_option:
                        filter_option = part
                    else:
                        raise CompileException(self._tag, 'Invalid variable')

                elif c.name == 'trans':
                    if not filter_option and in_filter_option:
                        filter_option = '_(%s)' % c.output_as_string()
                    else:
                        raise CompileException(self._tag, 'Invalid variable')

                if c.name == 'filter-option' and filter_name:
                    # Entered the colon ':'
                    in_filter_option = True

                elif c.name == 'pipe':
                    # | is the start of a following filter
                    return handle_filter(result(), children[i+1:])

            return result()

        def handle_var(children):
            out = []
            for i in range(0,len(children)):
                part = children[i].output_as_string()
                c = children[i]

                if c.name == 'digits':
                    # First digits are literals, following digits are indexers
                    out.append('[%s]' % part if out else part)

                elif c.name == 'dot':
                    #out.append('.') # assume last is not a dot
                    pass

                elif c.name == 'string':
                    out.append(part)

                elif c.name == 'name':
                    if out:
                        out.append('.%s' % part)
                    else:
                        if not self.variable_in_current_scope(part):
                            # If variable is not found in current or one of the parents'
                            # scopes, then prefix variable with "_c."
                            out.append('_c.%s' % part)
                        else:
                            out.append(part)

                elif c.name == 'trans':
                    if out:
                        raise CompileException(self._tag, 'Invalid variable')
                    else:
                        out.append('_(%s)' % handle_var(c.children))

                elif c.name == 'pipe':
                    # | is the start of a filter
                    return handle_filter(''.join(out), children[i+1:])
            return ''.join(out)

        return handle_var(tree.children)

    def get_code(self):
        self._flush_print_cache()
        return '\n'.join(self._code)

# ==================================[ Registration of template tags and filters ]===================================

# Dictionary for registering tags { tagname -> handler }
__tags = { }

class Tag(object):
    def __init__(self, tagname, optional=False):
        self.tagname = tagname
        self.is_optional = optional

def optional(tagname):
    """ Make a tagname optional.  """
    return Tag(tagname, optional=True)


def register_native_template_tag(start_tag, *other_tags):
    def turn_into_tag_object(tag):
        return Tag(tag) if isinstance(tag, basestring) else tag

    def decorator(func):
        __tags[start_tag] = func
        func.tags = map(turn_into_tag_object, other_tags)
    return decorator


_filters = { }
_native_filters = { }


def register_template_filter(name):
    def decorator(func):
        _filters[name] = func
    return decorator


def register_native_template_filter(name):
    def decorator(func):
        _native_filters[name] = func
    return decorator

# ==================================[ Compiler main loop ]===================================

def compile_tree(tree):
    """
    Turn parse tree into executable template code.
    """
    # We create some kind of tree hierarchy. The outer frames have to be
    # rendered before the inner frames.  This is opposed to Django's
    # parser/render engine, but we need this, because inner tags have to know
    # whether variabels are local scoped (from a parent frame), or come
    # directly from the context dictionary.

    generator = CodeGenerator()

    class TagFrameContent(object):
        def __init__(self, tagname):
            self.tagname = tagname
            self.content = []
            self.generator = None

        def render(self):
            for c in self.content:
                if isinstance(c, basestring):
                    generator.write_print(c)
                elif isinstance(c, Frame):
                    c.render()

        def render_indented(self):
            with generator.indent():
                self.render()

        @property
        def django_tags(self):
            """ Retreive the DjangoTag objects in this content frame """
            for c in self.content:
                if isinstance(c, TagFrame):
                    yield c.django_tag

        @property
        def django_variables(self):
            """ Retreive the DjangoVariable objects in this content frame """
            for c in self.content:
                if isinstance(c, VariableFrame):
                    yield c.django_variable

    class Frame(object): pass

    class TagFrame(Frame):
        """
        A frame is a series of matching template tags (like 'if'-'else'-'endif')
        with their content.
        """
        def __init__(self, django_tag, start_tag, other_tags, args=None):
            self.django_tag = django_tag # tag object
            self.start_tag = start_tag
            self.other_tags = other_tags # list of Tag
            self.args = args or []       # Tag args parameters
            self.handler = None  # Tag handler
            self.frame_content = [ ] # List of TagFrameContent

        @property
        def following_tagnames(self):
            """ Next optional tags, or first following required tag """
            for t in self.other_tags:
                if t.is_optional:
                    yield t.tagname
                else:
                    yield t.tagname
                    return

        def start_content_block(self, tagname):
            removed_tag = False
            while not removed_tag and len(self.other_tags):
                if self.other_tags[0].tagname == tagname:
                    removed_tag = True
                self.other_tags = self.other_tags[1:]

            content = TagFrameContent(tagname)
            self.frame_content.append(content)

        def append_content(self, content):
            if not self.frame_content:
                 self.frame_content.append(TagFrameContent(self.start_tag))
            self.frame_content[-1].content.append(content)

        def render(self):
            if self.handler:
                self.handler(generator.tag_proxy(self.django_tag), self.args, *self.frame_content)
            else:
                for c in self.frame_content:
                    c.render()

    class VariableFrame(Frame):
        def __init__(self, django_variable):
            self.django_variable = django_variable

        def render(self):
            generator.write('_w(%s)' %
                    generator.tag_proxy(self.django_variable).convert_variable(self.django_variable.varname))

    class BlocktransFrame(Frame):
        def __init__(self, tag):
            self.tag = tag

        def render(self):
            handle_blocktrans(generator.tag_proxy(self.tag), self.tag)

    def run():
        # Push/pop stack for the Django tags.
        stack = [ TagFrame(None, 'document', [ Tag('enddocument') ]) ]

        def top():
            return stack[-1] if stack else None

        def _compile(n):
            if isinstance(n, DjangoTag):
                if n.tagname in __tags:
                    # Opening of {% tag %}
                    other_tags = __tags[n.tagname].tags
                    frame = TagFrame(n, n.tagname, other_tags, n.args)
                    frame.handler = __tags[n.tagname]

                    if other_tags:
                        stack.append(frame)
                    else:
                        top().append_content(frame)

                elif stack and n.tagname == top().other_tags[-1].tagname:
                    # Close tag for this frame
                    frame = stack.pop()
                    top().append_content(frame)

                elif stack and n.tagname in top().following_tagnames:
                    # Transition to following content block (e.g. from 'if' to 'else')
                    top().start_content_block(n.tagname)

                else:
                    raise CompileException(n, 'Unknown template tag %s' % n.tagname)

            elif isinstance(n, DjangoVariable):
                top().append_content(VariableFrame(n))

            elif isinstance(n, basestring):
                top().append_content(n)

            elif isinstance(n, DjangoTransTag):
                top().append_content(_(n.string))

            elif isinstance(n, DjangoBlocktransTag):
                # Create blocktrans frame
                top().append_content(BlocktransFrame(n))

            elif any([ isinstance(n, k) for k in (DjangoPreprocessorConfigTag, DjangoComment, DjangoMultilineComment, DjangoLoadTag, DjangoCompressTag) ]):
                pass

            elif any([ isinstance(n, k) for k in (DjangoContent, HtmlNode, DjangoRawOutput) ]):
                # Recursively build output frames
                n.output(_compile)

            else:
                raise CompileException(n, 'Unknown django tag %s' % n.name)

        tree.output(_compile)

        stack[0].render()

        return generator.get_code()
    return run()


def handle_blocktrans(generator, tag):
    """
    Handle {% blocktrans with value as name ...%} ... {% endblocktrans %}
    """
    # TODO: {% plural %} support

    variables = []
    string = []

    for c in tag.children:
        if isinstance(c, DjangoVariable):
            variables.append(c.varname)
            string.append('%%(%s)s' % c.varname)
        elif isinstance(c, basestring):
            string.append(c)  # TODO: escape %
        else:
            string.append(c.output_as_string())  # TODO: escape %

    # TODO: wrap in 'with' block


    if variables:
        generator.write('_w(_("""%s""") %% { %s })' % (
                                ''.join(string).replace('"', r'\"'),
                                ','.join(['"%s":%s' % (v, generator.convert_variable(v)) for v in variables ])
                                ))
    else:
        generator.write('_w(_("""%s"""))' % ''.join(string))

    """
    def __(b, c):
        _w("%(b)s ... %(c)s" % { 'b': b, 'c': c })
    __(_c.a,_c.d)

    # {% blocktrans with a as b and d as c %}{{ b }} ... {{ c }}{% endblocktrans %}
    """



def register_template_tag(tagname, *other_tags):
    """
    Register runtime-evaluated template tag.
    """
    def decorator(func):
        @register_native_template_tag(tagname, *other_tags)
        def native_implementation(generator, args, *content):
            i = 0
            for c in content:
                generator.write('def __%s():' % i)
                c.render_indented()
                i += 1
            generator.write('_call_tag(%s, %s, %s)' %
                (unicode(args), ','.join(map(lambda i: '__%s' % i, range(0, len(content))))))

            """
            def __c1():
                ...
            def __c2():
                ...
            def __c3():
                ...
            _call_tag('tag_handler', args, __c1, __c2, __c3)
            """

        # TODO: store binding between func and native implementation somewhere.
        # _call_tag('tag_handler') -> func
        # TODO: pass context or loookup method

    return decorator





# ==================================[ Code execution environment ]===================================

class OutputCapture(list):
    """
    Simple interface for capturing the output, and stacking
    several levels of capturing on top of each other.

    We inherit directly from list, for performance reasons.
    It faster than having a member object of type list, and
    doing a lookup every time.
    """
    def __init__(self):
        self.sink_array = []
        self.level = 0

        # Redirect stdout to capture interface
        # (for parts of code doing print or sys.stdout.write
        class StdOut(object):
            def write(s, c):
                self.append(c)

        self._old_stdout = sys.stdout
        sys.stdout = StdOut()

    def capture(self):
        # Copy current list to stack
        self.sink_array.append(list(self))

        # Create new sink
        list.__init__(self) # Empty capture list

        self.level += 1

    def __call__(self, c):
        self.append(c)

    def end_capture(self):
        if self.level:
            # Join last capture
            result = u''.join(map(unicode,self))
            self.level -= 1

            # Pop previous capture
            list.__init__(self)
            self.extend(self.sink_array.pop())

            return result
        else:
            raise Exception("'end_capture' called without any previous call of 'capture'")

    def end_all_captures(self):
        # Restore stdout
        sys.stdout = self._old_stdout

        # Return captured content
        out = ''
        while self.level:
            out = self.end_capture()
        return out


class ContextProxy(object):
    """
    Proxy for a Django template Context, this will handle the various attribute lookup
    we can do in a template. (A template author does not have to know whether something is
    an attribute or index or callable, we decide at runtime what to do.)
    """
    def __init__(self, context=''):
        self._context = context or '' # Print an empty string, rather than 'None'

    def __str__(self):
        return str(self._context)

    def __unicode__(self):
        return unicode(self._context)

    def __add__(self, other):
        """ Implement + operator """
        if isinstance(other, ContextProxy):
            other = other._context
        return ContextProxy(self._context + other)

    def __sub__(self, other):
        """ Implement - operator """
        if isinstance(other, ContextProxy):
            other = other._context
        return ContextProxy(self._context - other)

    def __iter__(self):
        try:
            return self._context.__iter__()
        except AttributeError:
            # Dummy iterator
            return [].__iter__()

    def __nonzero__(self):
        return bool(self._context)

    def __len__(self):
        return len(self._context)

    def __call__(self, *args, **kwargs):
        try:
            return ContextProxy(self._context(*args, **kwargs))
        except TypeError:
            return ContextProxy()

    def __getattr__(self, name):
        # Similar to django.template.Variable._resolve_lookup(context)
        # But minor differences: `var.0' is in our case compiled to var[0]
        # Do we can a quick list index lookup, before dictionary lookup of the string "0".
        c = self._context

        try:
            attr = c[name]
            if callable(attr): attr = attr()
            return ContextProxy(attr)
        except (IndexError, ValueError, TypeError, KeyError, AttributeError):
            try:
                attr = getattr(c, name)
                if callable(attr): attr = attr()
                return ContextProxy(attr)
            except (TypeError, AttributeError):
                try:
                    attr = c[str(name)]
                    if callable(attr): attr = attr()
                    return ContextProxy(attr)
                except (KeyError, AttributeError, TypeError):
                    return ContextProxy()

    def __getitem__(self, name):
        c = self._context

        try:
            attr = c[name]
            if callable(attr): attr = attr()
            return ContextProxy(attr) # Print an empty string, rather than 'None'
        except (IndexError, ValueError, TypeError, KeyError):
            try:
                attr = c[str(name)]
                if callable(attr): attr = attr()
                return ContextProxy(attr)
            except (KeyError, AttributeError, TypeError):
                return ContextProxy()




class Template(object):
    """
    Create a Template-compatible object.
    (The API is compatible with django.template.Template, but it wraps around the faster
    template compiled as python code.)
    """
    def __init__(self, compiled_template_code, filename):
        from __builtin__ import compile
        self._code = compiled_template_code
        self.compiled_template_code = compile(compiled_template_code, 'Python compiled template: %s' % filename, 'exec')

    def render(self, context):
        a = self._code
        capture_interface = OutputCapture()
        capture_interface.capture()
        from django.core.urlresolvers import reverse

        our_globals = {
            'capture_interface': capture_interface, # Rendered code may call the capture interface.
            '_w': capture_interface,
            '_c': ContextProxy(context),
            '_f': _filters,
            '_p': ContextProxy,
            '_for': ForLoop,
            '_cycle': Cycle,
            'reverse':  reverse,
            '_': _,
            'sys': sys,
        }

        exec (self.compiled_template_code, our_globals, our_globals)

        # Return output
        return capture_interface.end_all_captures()



# ================================[ TEMPLATE TAG IMPLEMENTATIONS ]================================



@register_template_tag('has_permission', 'end_haspermission')
def has_permission(args):
    name = params[0]
    if lookup('request.user').has_permission(name): # TODO: receive context or lookup method
        content()


@register_native_template_tag('url')
def url(generator, args):
    """
    Native implementation of {% url %}
    """
    # Case 1: assign to varname
    if len(args) >= 2 and args[-2] == 'as':
        varname = args[-1]
        args = args[:-2]

        prefix = '%s = ' % varname
        suffix = ''
        generator.register_variable(varname)

    # Case 2: print url
    else:
        prefix = '_w('
        suffix = ')'

    def split_args_and_kwargs(params):
        args = []
        kwargs = { }
        for k in params:
            if '=' in k:
                k,v = k.split('=', 1)
                kwargs[unicode(k)] = generator.convert_variable(v)
            else:
                args.append(generator.convert_variable(k))

        return args, kwargs


    name = args[0]
    args, kwargs = split_args_and_kwargs(args[1:])

    generator.write('%s reverse("%s", args=%s, kwargs={%s})%s' %
            (
            prefix,
            unicode(name),
            '[%s]' % ','.join(args),
            ','.join(['"%s":%s' % (unicode(k), v) for k,v in kwargs.iteritems() ]),
            suffix
            ))


@register_native_template_tag('with', 'endwith')
def with_(generator, args, content):
    """
    {% with a as b and c as d %} ... {% endwith %}
    """
    pairs = { } # key -> value

    value = None
    passed_as = False

    for k in args:
        if k == 'and':
            pass
        elif k == 'as':
            passed_as = True
        else:
            if passed_as and value:
                # Remember pair
                pairs[k] = value
                value = None
                passed_as = False
            elif not value:
                value = k
            else:
                raise 'invalid syntax'#TODO

    with generator.scope():
        for name in pairs.keys():
            generator.register_variable(name);

        generator.write('def __(%s):' % ','.join(pairs.keys()))
        content.render_indented()
        generator.write('__(%s)' % ','.join(map(generator.convert_variable, pairs.values())))

    """
    def __(b):
        ...
    __(_c.a)
    """


@register_native_template_tag('filter', 'endfilter')
def filter(generator, args, content):
    """
    Native implementation of {% filter ... %} ... {% endfilter %}
    """
    filter_name, = args

    generator.write('_start_capture()')
    generator.write('def __():')
    content.render_indented()
    generator.write('__():')
    generator.write("print _filters['%s'](_stop_capture())," % filter_name)


    """
    _start_capture() # Push stdout stack
    def __():
        ...
    __()
    print _filters['escape'] (_stop_capture) # Pop stdout stack, call filter, and print
    """


@register_native_template_tag('if', optional('else'), 'endif')
def if_(generator, args, content, else_content=None):
    """
    Native implementation of the 'if' template tag.
    """
    operators = ('==', '!=', '<', '>', '<=', '>=', 'and', 'or', 'not', 'in')

    params = map(lambda p: p if p in operators else generator.convert_variable(p), args)

    generator.write('if %s:' % ' '.join(params))
    content.render_indented()

    if else_content:
        generator.write('else:')
        else_content.render_indented()


    """
    if condition:
        ...
    else:
        ...
    """


@register_native_template_tag('pyif', optional('else'), 'endpyif')
def pyif_(generator, args, content, else_content=None):
    """
    {% pyif ... %}
    """
    # It is pretty tricky to do a decent convertion of the variable names in this case,
    # therefor, we execute the pyif test in an eval, and pass everything we 'think' that
    # could be a variable into a new context. There is certainly a better implementation,
    # but this should work, and pyif is not recommended anyway.

    def find_variables():
        import re
        variable_re = re.compile(r'[a-zA-Z][a-zA-Z0-9_]*')

        vars = set()
        for a in args:
            for x in variable_re.findall(a):
                if not x in ('and', 'or', 'not', 'in'):
                    vars.add(x)
        return vars

    def process_condition():
        import re
        part_re = re.compile(
            '(' +
                # Django variable name with filter or strings
                r'([a-zA-Z0-9_\.\|:]+|"[^"]*"|\'[^\']*\')+'

            + '|' +
                # Operators
                r'([<>=()\[\]]+)'
            ')'
        )
        operator_re = re.compile(r'([<>=()\[\]]+|and|or|not|in)')

        o = []
        for a in args:
            y = part_re.findall(a)
            for x in part_re.findall(a):
                if isinstance(x,tuple): x = x[0]
                if operator_re.match(x):
                    o.append(x)
                else:
                    o.append(generator.convert_variable(x))
        return ' '.join(o)

    generator.write('if (%s):' % process_condition())
    content.render_indented()

    if else_content:
        generator.write('else:')
        else_content.render_indented()


@register_native_template_tag('ifequal', optional('else'), 'endifequal')
def ifequal(generator, args, content, else_content=None):
    """
    {% ifequal %}
    """
    a, b = args

    generator.write('if %s == %s:' % (generator.convert_variable(a), generator.convert_variable(b)))
    content.render_indented()

    if else_content:
        generator.write('else:')
        else_content.render_indented()


    """
    if a == b:
        ...
    else:
        ...
    """

@register_native_template_tag('ifnotequal', optional('else'), 'endifnotequal')
def ifnotequal(generator, args, content, else_content=None):
    """
    {% ifnotequal %}
    """
    a, b = args

    generator.write('if %s != %s:' % (generator.convert_variable(a), generator.convert_variable(b)))
    content.render_indented()

    if else_content:
        generator.write('else:')
        else_content.render_indented()


@register_native_template_tag('for', optional('empty'), 'endfor')
def for_(generator, args, content, empty_content=None):
    """
    {% for item in iterator %}
        {{ forloop.counter }}
        {{ forloop.counter0 }}
        {{ forloop.revcounter0 }}
        {{ forloop.first }}
        {{ forloop.last }}
        {{ forloop.parentloop }}
        {% ifchanged var.name %}... {% endifchanged %}

        {% if forloop.first %} ... {% endif %}

        {% cycle "a" "b" %}
    {% empty %}
    {% endfor %}

    {% for x in a b c %}
        ...
    {% endfor %}
    """
    if len(args) > 3:
        var, in_ = args[0:2]
        iterator = args[3:]
    else:
        var, in_, iterator = args

    # === Implementation decision ===

    # We have two implementations of the forloop

    # 1. The Quick forloop. Where the forloop variable is not accessed anywhere
    #    inside the forloop. And where no empty statement is used.

    # 2. The slower, more advanced forloop. Which exposes a forloop object,
    #    exposes all the forloop properties, and allows usage of {% ifchanged %}
    quick_forloop = True

    if empty_content:
        quick_forloop = False

    for t in content.django_tags:
        if t.tagname in ('cycle', 'ifchanged'):
            quick_forloop = False

    for v in content.django_variables:
        if 'forloop' in v.varname:
            quick_forloop = False

            # TODO: chooose complex implementation when using {% if forloop.first %} somewhere.


    # === implementations ===

    if quick_forloop:
        with generator.scope():
            generator.register_variable(var);

            generator.write('def __():')
            with generator.indent():
                generator.write('for %s in %s:' % (var, generator.convert_variable(iterator)))
                with generator.indent():
                    generator.write('%s=_p(%s)' % (var, var))
                    content.render()
            generator.write('__()')

    else:
        # Forloop body
        with generator.scope():
            generator.register_variable(var);
            generator.register_variable('forloop');

            generator.write('def __(forloop, %s):' % var)
            content.render_indented()

        # Empty content body
        if empty_content:
            generator.write('def __e():')
            empty_content.render_indented()

        # Forloop initialisation
        generator.write('_for(%s, __, %s, %s)' % (
                                generator.convert_variable(iterator),
                                ('__e' if empty_content else 'None'),
                                'None' # TODO: pass parentloop, if we have one.
                            ))

    """
    # Quick implementation
    def __():
        for item in iterator:
            print ...
    __()

    # Advanced
    def __():
        for __(forloop):
            ...(content)...
        def __e(forloop, item):
            ...(empty)...
        --()
        _for(iterator, __, __e, forloop)
    __()
    """


class ForLoop(object):
    def __init__(self, iterator, body, empty_body, parent=None):
        self._iterator = iter(iterator)
        self._first = True
        self._last = False
        self._parent = parent
        self._counter = 0
        self._if_changed_storage = { }

        try:
            # Read first item
            current = self._iterator.next()

            # Read next item
            try:
                next_ = self._iterator.next()
            except StopIteration, e:
                self._last = True

            while True:
                # Call forloop body
                body(self, ContextProxy(current))

                # Go to next
                if self._last:
                    return
                else:
                    # Update current
                    self._counter += 1
                    current = next_

                    # Update next (not DRY, but it would cause too much function
                    # calling overhead otherwise...)
                    try:
                        next_ = self._iterator.next()
                    except StopIteration, e:
                        self._last = True

        except StopIteration, e:
            if empty_body:
                empty_body()

    @property
    def _ifchanged(self, varname, new_value):
        """
        In-forloop storage for checking wether this value has been changed,
        compared to last call. Called by {% ifchanged varname %} template tag.
        """
        self._if_changed_storage = { }
        prev_value = self._if_changed_storage.get(varname, None)
        changed = prev_value != new_value
        self._if_changed_storage[varname] = new_value
        return changed

    @property
    def first(self):
        return self._first

    @property
    def last(self):
        raise self._last

    @property
    def counter(self):
        return self._counter + 1

    @property
    def counter0(self):
        return self._counter

    @property
    def revcounter0(self):
        raise Exception('{{ forloop.revcounter0 }} not yet implemented')

    @property
    def parentloop(self):
        return self._parent or ContextProxy()

    def __getattr__(self):
        """
        For any undefined property, return this dummy proxy.
        """
        return ContextProxy()

class Cycle(object):
    def __init__(self, *args):
        self._args = args
        self._len = len(args)
        self._display_counter = 0

    @property
    def next(self):
        sys.stdout.write(self._args[self._display_counter % self._len ])
        self._display_counter += 1


@register_native_template_tag('cycle')
def cycle(generator, args):
    """ {% cycle v1 v2 v3 as varname %} """ # Not required to be nested inside a forloop, assigned to iterator
    """ {% cycle varname %} """ # Iterator ++; and output
    """ {% cycle v1 v2 v3 %} """ # cycle inside forloop.
    if 'as' in args:
        args, as_, varname = args[:-2], args[-2], args[-1]
        generator.register_variable(varname)
        generator.write('%s = _cycle(%s)' % (varname, ','.join(map(generator.convert_variable, args))))

    elif len(args) == 1:
        varname, = args

        if not generator.variable_in_current_scope(varname):
            raise CompileException(generator.current_tag, 'Variable %s has not been defined by a {% cycle %} declaration' % varname)

        generator.write('%s.next' % generator.convert_variable(varname))

    else:
        # How it works: {% for %} should detect wether some {% cycle %} nodes are nested inside
        if not generator.variable_in_current_scope('forloop'):
            raise CompileException(generator.current_tag, '{% cycle %} can only appear inside a {% for %} loop')

        args = map(generator.convert_variable, args)
        generator.write('sys.stdout.write([ %s ][ forloop.counter %% %i ])' % (','.join(args), len(args)))


    """
    varname = _cycle(v1, v2, v3)
    varname.next
    varname = [ v1, v2, v3 ] [ forloop.counter % 3 ]
    """


@register_native_template_tag('csrf_token')
def csrf_token(generator, args):
    """ {% csrf_token %} """
    # The django implementation checks if _c.csrf_token return 'NOTPROVIDED', and if so, it doesn't print
    # the hidden field. We don't place this if test in the generated code.
    generator.write_print('<div style="display:none"><input type="hidden" name="csrfmiddlewaretoken" value="')
    generator.write('sys.stdout.write(_c.csrf_token)')
    generator.write_print('" /></div>')


@register_native_template_tag('widthratio')
def widthratio(generator, args):
    """
    {% widthratio this_value max_value 100 %}
    """
    a, b, c = map(generator.convert_variable, args)
    generator.write('_w(int(%s / %s * %s))' % (a, b, c))


@register_native_template_tag('now')
def now_(generator, args):
    """
    {% now 'Y' format %}
    """
    format_, = map(generator.convert_variable, args)

    generator.write('def __():')
    with generator.indent():
        generator.write('from datetime import datetime')
        generator.write('from django.utils.dateformat import DateFormat')
        generator.write('sys.stdout.write(DateFormat(datetime.now()).format(%s))' % generator.convert_variable(format_))
    generator.write('__()')


@register_native_template_tag('call')
def call_template_tag(generator, args):
    """
    {% call func p1 p2 %}
    {% call result = func p1 p2 %}
    """
    if '=' in args:
        result = args[0]
        assert args[1] == '='
        func = generator.convert_variable(args[2])
        p = map(generator.convert_variable, args[3:])

        generator.register_variable(result)
        generator.write('%s = %s(%s)' % (result, func, ','.join(p)))
    else:
        func = generator.convert_variable(args[0])
        p = map(generator.convert_variable, args[1:])

        generator.write('sys.stdout.write(%s(%s))' % (func, ','.join(p)))


@register_native_template_tag('get_pingback_url')
def get_pingback_url(generator, args, *content):
    pass # TODO: and move to mvno platform

@register_native_template_tag('get_flattext')
def get_flattext(generator, args, *content):
    pass # TODO: and move to mvno platform

@register_native_template_tag('blog_latest_items')
def get_flattext(generator, args, *content):
    pass # TODO: and move to mvno platform

@register_native_template_tag('get_trackback_rdf_for')
def get_trackback_rdf_for(generator, args, *content):
    pass # TODO: and move to mvno platform

@register_native_template_tag('paginate', 'endpaginate')
def paginate(generator, args, paginated_content):
    pass # TODO: and move to mvno platform



@register_native_template_filter('add')
def add(generator, subject, arg):
    """ {{ var|add:"var" }} """ # TODO: arg should be converted to variables before calling filter
    return '(%s + %s)' % (subject, generator.convert_variable(arg))


@register_native_template_filter('default')
def default(generator, subject, arg):
    """ {{ var|default:"var" }} """
    return '(%s or %s)' % (subject, generator.convert_variable(arg))


@register_native_template_filter('empty')
def empty(generator, subject, arg):
    """ {{ var|empty:_("N/A) }} """
    #  TODO Same to |default filter???
    return '(%s or %s)' % (subject, generator.convert_variable(arg))



@register_native_template_filter('default_if_none')
def default_if_none(generator, subject, arg):
    """ {{ var|default_if_none:"var" }} """
        # TODO: may not be the best way, subject can be a complex object, and this causes it to be resolved twice.
    return '(%s if %s is None else %s)' % (subject, subject, generator.convert_variable(arg))

@register_native_template_filter('cut')
def cut(generator, subject, arg):
    """ {{ var|cut:" " }} """
    return 'unicode(%s).replace(%s, '')' % (subject, generator.convert_variable(arg))

@register_native_template_filter('replace')
def cut(generator, subject, arg):
    """ {{ var|replace:"a|b" }} """
    a, b = arg.strip('"').strip("'").split('|')
    return 'unicode(%s).replace("%s", "%s")' % (subject, a, b)

@register_native_template_filter('slice')
def slice(generator, subject, arg):
    """ {{ var|slice:":2"}} """
    a,b = arg.strip('"').strip("'").split(':')
    return '(%s[%s:%s])' % (subject,
            (int(a) if a else ''),
            (int(b) if b else ''))


@register_native_template_filter('divisibleby')
def divisibleby(generator, subject, arg):
    """ {{ var|divisibleby:3 }} """
    return '(%s %% %s == 0)' % (subject, generator.convert_variable(arg))


@register_native_template_filter('first')
def first(generator, subject, arg):
    """ {{ var|first }} """
    return '(%s[0])' % (subject)


@register_native_template_filter('join')
def join(generator, subject, arg):
    """ {{ var|join }} """
    return '(%s.join(%s))' % (generator.convert_variable(arg), subject)

@register_native_template_filter('safe')
def safe(generator, subject, arg):
    """ {{ var|safe }} """
    return subject # TODO

@register_native_template_filter('length')
def length(generator, subject, arg):
    """ {{ var|length}} """
    return 'len(%s)' % subject

@register_native_template_filter('pluralize')
def pluralize(generator, subject, arg):
    """ {{ var|pluralize }} """ # appends 's'
    """ {{ var|pluralize:"suffix" }} """
    """ {{ var|pluralize:"single,plural" }} """
    return subject # TODO

@register_native_template_filter('date')
def date(generator, subject, arg):
    """ {{ var|date:format }} """
    return subject # TODO

@register_native_template_filter('truncate_chars')
def truncate_chars(generator, subject, arg):
    """ {{ var|truncate_chars:2}} """
    return '%s[:%s]' % (subject, int(arg))

@register_native_template_filter('floatformat')
def floatformat(generator, subject, arg):
    """ {{ var|floatformat:"-3" }} """
    return subject # TODO


@register_native_template_filter('prettify_phonenumber')
def prettify_phonenumber(generator, subject, arg):
    """ {{ var|safe }} """
    return subject # TODO

@register_native_template_filter('dictsort')
def dictsort(generator, subject, arg):
    """ {{ var|dictsort:"key"}} """
    return 'sorted(%s, key=(lambda i: getattr(i, %s)))' % (subject, generator.convert_variable(arg))

@register_native_template_filter('dictsortreversed')
def dictsortreversed(generator, subject, arg):
    """ {{ var|dictsort:"key"}} """
    return 'sorted(%s, key=(lambda i: getattr(i, %s)), reverse=True)' % (subject, generator.convert_variable(arg))

#=================

@register_template_filter('capfirst')
def capfirst(subject):
    """ {{ value|capfirst }} """
    return subject[0].upper() + subject[1:]


@register_template_filter('striptags')
def striptags(subject):
    """Strips all [X]HTML tags."""
    from django.utils.html import strip_tags
    return strip_tags(subject)
    # TODO make safe string


# All django filters can be wrapped as non-native filters...
