#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Django template preprocessor.
Author: Jonathan Slenders, City Live
"""
from django_processor import parse


def output_tree(tree):
    return tree.output_as_string()


def _default_loader(path):
    return open(path).read()


def compile(code, loader=None, path='', options=None):
    """
    Compile the template, do everything, and return a single document
    as a string. The loader should look like: (lambda path: return code)
    and is called for the includes/extends.
    """
    tree = compile_to_parse_tree(code, loader, path, options)

    #print tree._print()
    #print output_tree(tree)

    return output_tree(tree)


def compile_to_parse_tree(code, loader=None, path='', options=None):
    # Make the loader also parse the templates
    def new_loader(include_path):
        return parse( (loader or _default_loader)(include_path), include_path, new_loader)

    # Parse template, and return output
    return parse(code, path, new_loader, main_template=True, options=options)
