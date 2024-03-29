#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Django template preprocessor.
Author: Jonathan Slenders, City Live
"""

"""
Tokenizer for a template preprocessor.
------------------------------------------------------------------
This file contains only the classes used for defining the grammar of each
language. The actual engine can be found in lexer_engine.py

The Token class is the base class for any node in the parse tree.
"""

__author__ = 'Jonathan Slenders, City Live'
__all__ = ('lex', 'Token')

import re
import itertools


class CompileException(Exception):
    def __init__(self, *args):
        """
        Call:
        CompileException(message)
        CompileException(token, message)
        CompileException(line, column, path, message)
        """
        if isinstance(args[0], basestring):
            self.line, self.column, self.path, self.message = 0, 0, '', args[0]

        elif isinstance(args[0], Token):
            if args[0]:
                # TODO: eleminate call like CompileException(None, message)
                self.path = args[0].path
                self.line = args[0].line
                self.column = args[0].column
                self.message = args[1]
            else:
                self.path = self.line = self.column = '?'
        else:
            self.line, self.column, self.path, self.message = args


        Exception.__init__(self,
            u'In: %s\nLine %s, column %s: %s' % (self.path, self.line, self.column, self.message))


class Token(object):
    """
    Token in the parse tree
    """
    def __init__(self, name='unknown-node', line=0, column=0, path=''):
        self.name = name
        self.line = line
        self.path = path
        self.column = column
        self.children = [] # nest_block_level_elements can also create a .children2, .children3 ...
        self.params = [] # 2nd child list, used by the parser

    def append(self, child):
        self.children.append(child)

    @property
    def children_lists(self):
        """
        Yield all the children child lists.
        e.g. "{% if %} ... {% else %} ... {% endif %}" has two child lists.
        """
        yield self.children

        i = 2
        while hasattr(self, 'children%i' % i):
            yield getattr(self, 'children%i' % i)
            i += 1

    @property
    def all_children(self):
        return list(itertools.chain(* list(self.children_lists)))

    def get_childnodes_with_name(self, name):
        for children in self.children_lists:
            for c in children:
                if c.name == name:
                    yield c

    def is_i(self, class_):
        """
        node.is(TokenClass)
        is synonym for:
        isinstance(node, TokenClass)
        """
        return isinstance(self, class_)

    def _print(self, prefix=''):
        """
        For debugging: print the output to a unix terminal for a colored parse tree.
        """
        result = []

        result.append('\033[34m')
        result.append ("%s(%s,%s) %s {\n" % (self.name, str(self.line), str(self.column), self.__class__.__name__))
        result.append('\033[0m')

        children_result = []
        for t in self.children:
            if isinstance(t, basestring):
                children_result.append('str(%s)\n' % t)
            else:
                children_result.append("%s\n" % t._print())
        result.append(''.join(['\t%s\n' % s for s in ''.join(children_result).split('\n')]))

        result.append('\033[34m')
        result.append("}\n")
        result.append('\033[0m')
        return ''.join(result)

    def output(self, handler):
        """
        Method for generating the output.
        This calls the output handler for every child of this node.
        To be overriden in the parse tree. (an override can output additional information.)
        """
        for children in self.children_lists:
            for c in children:
                handler(c)

    def _output(self, handler):
        """
        Original output method.
        """
        for children in self.children_lists:
            for c in children:
                handler(c)

    def output_as_string(self, use_original_output_method=False, hook_dict=None):
        """
        Return a unicode string of this node
        The `hook_dict` parameter can be used to override the output behaviour of
        certain classes, and insert own output hooks instead.
        !! Ensure that the classes in hook_dict have no parent/child relationship,
           every isinstance match will be called.
        """
        hook_dict = hook_dict or { }
        o = []
        def capture(s):
            if any(isinstance(s, k) for k in hook_dict):
                for k in hook_dict:
                    if isinstance(s, k):
                        o.append(hook_dict[k](s))

            elif isinstance(s, basestring):
                o.append(s)

            elif use_original_output_method:
                s._output(capture)

            else:
                s.output(capture)

        if use_original_output_method:
            self._output(capture)
        else:
            self.output(capture)

        return u''.join(o)

    def output_params(self, handler):
        for c in self.params:
            handler(c)

    def __unicode__(self):
        """ Just for debugging the parser """
        return self._print()

    # **** [ Token manipulation ] ****

    def child_nodes_of_class(self, classes, dont_enter=None):
        """
        Iterate through all nodes of this class type.
        (I think it's a depth-first implementation.)
        `dont_enter` parameter can receive a list of
        """
        for children in self.children_lists:
            for c in children:
                if any([ isinstance(c, t) for t in classes ]):
                    yield c

                if isinstance(c, Token):
                    if not any([isinstance(c, t) for t in dont_enter or [] ]):
                        for i in c.child_nodes_of_class(classes, dont_enter):
                            yield i

    def remove_child_nodes_of_class(self, class_, except_nodes=None):
        """
        Iterate recursively through the parse tree,
        and remove nodes of this class.
        """
        except_nodes = except_nodes or []

        for children in self.children_lists:
            for c in children[:]:
                if isinstance(c, class_) and not c in except_nodes:
                    children.remove(c)

                if isinstance(c, Token):
                    c.remove_child_nodes_of_class(class_)

    def remove_child_nodes(self, nodes):
        """
        Removed these nodes from the tree.
        """
        for children in self.children_lists:
            for c in children[:]:
                if c in nodes:
                    children.remove(c)

                if isinstance(c, Token):
                    c.remove_child_nodes(nodes)

    def collapse_nodes_of_class(self, class_):
        """
        Replace nodes of this class by their children.
        """
        for children in self.children_lists:
            new_nodes = []
            for c in children:
                if isinstance(c, Token):
                    c.collapse_nodes_of_class(class_)

                if isinstance(c, class_):
                    new_nodes += c.children
                else:
                    new_nodes.append(c)

            children.__init__(new_nodes)


class State(object):
    """
    Parse state. Contains a list of regex we my find in the current
    context. Each parse state consists of an ordered list of transitions.
    """
    class Transition(object):
        def __init__(self, regex_match, action_list):
            """
            Parse state transition. Consits of a regex
            and an action list that should be executed whet
            this regex has been found.
            """
            self.regex_match = regex_match
            self.compiled_regex = re.compile(regex_match)
            self.action_list = action_list

    def __init__(self, *transitions):
        self.__transitions = transitions

    def transitions(self):
        """ Transition iterator """
        for t in self.__transitions:
            yield t.compiled_regex, t.action_list


###
# Following classes are 'action' classes for the tokenizer
# Used for defining the grammar of a language
###

class ParseAction(object):
    """ Abstract base class, does nothing. """
    pass

class Push(ParseAction):
    """
    Push this state to the state tack. Parsing
    shall continue by examining this state.
    """
    def __init__(self, state_name):
        self.state_name = state_name

class Pop(ParseAction):
    """
    Pop from the state stack.
    """
    pass

class Record(ParseAction):
    """
    Record the matched text into the current
    token.
    """
    def __init__(self, value=None):
        self.value = value

class Shift(ParseAction):
    """
    Shift the parse pointer after the match.
    """
    pass

class StartToken(ParseAction):
    """
    Push this token to the parse stack. New
    tokens or records shall be inserted as
    child of this one.
    """
    def __init__(self, state_name):
        self.state_name = state_name

class StopToken(ParseAction):
    """
    Pop the current token from the parse stack.
    """
    def __init__(self, state_name=None):
        self.state_name = state_name

class Error(ParseAction):
    """
    Raises an error. We don't expect this match here.
    """
    def __init__(self, message):
        self.message = message

