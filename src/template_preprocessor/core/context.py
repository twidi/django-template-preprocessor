#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Django template preprocessor.
Author: Jonathan Slenders, City Live
"""
from template_preprocessor.core.lexer import CompileException

class Context(object):
    """
    Preprocess context. Contains the compile settings, error logging,
    remembers dependencies, etc...
    """
    def __init__(self, path, loader=None, extra_options=None):
        self.loader = loader

        self.warnings = []
        self.template_dependencies = []
        self.media_dependencies = []

        # Process options
        self.options = Options()
        for o in extra_options or []:
            self.options.change(o)

    def raise_warning(self, node, message):
        """
        Log warnings: this will not raise an exception. So, preprocessing
        for the current template will go on. But it's possible to retreive a
        list of all the warnings at the end.
        """
        self.warnings.append(PreprocessWarning(node, message))

    def load(self, template):
        if self.loader:
            self.template_dependencies.append(template)
            return self.loader(template)
        else:
            raise Exception('Preprocess context does not support template loading')


class PreprocessWarning(Warning):
    def __init__(self, node, message):
        self.node = node
        self.message = message


class Options(object):
    """
    What options are used for compiling the current template.
    """
    def __init__(self):
        # Default settings
        self.whitespace_compression = True
        self.preprocess_translations = True
        self.preprocess_urls = True
        self.preprocess_variables = True
        self.remove_block_tags = True # Should propably not be disabled
        self.merge_all_load_tags = True
        self.execute_preprocessable_tags = True
        self.preprocess_macros = True
        self.preprocess_ifdebug = True # Should probably always be True
        self.remove_some_tags = True # As we lack a better settings name

        # HTML processor settings
        self.is_html = True

        self.compile_css = True
        self.compile_javascript = True
        self.ensure_quotes_around_html_attributes = False # Not reliable for now...
        self.merge_internal_css = False
        self.merge_internal_javascript = False # Not always recommended...
        self.remove_empty_class_attributes = False
        self.pack_external_javascript = False
        self.pack_external_css = False
        self.validate_html = True
        self.disallow_orphan_blocks = False # An error will be raised when a block has been defined, which is not present in the parent.

    def change(self, value, node=None):
        """
        Change an option. Called when the template contains a {% ! ... %} option tag.
        """
        actions = {
            'whitespace-compression': ('whitespace_compression', True),
            'no-whitespace-compression': ('whitespace_compression', False),
            'merge-internal-javascript': ('merge_internal_javascript', True),
            'merge-internal-css': ('merge_internal_css', True),
            'html': ('is_html', True), # Enable HTML extensions
            'no-html': ('is_html', False), # Disable all HTML specific options
            'no-macro-preprocessing': ('preprocess_macros', False),
            'html-remove-empty-class-attributes': ('remove_empty_class_attributes', True),
            'pack-external-javascript': ('pack_external_javascript', True),
            'pack-external-css': ('pack_external_css', True),
            'compile-css': ('compile_css', True),
            'compile-javascript': ('compile_javascript', True),
            'validate-html': ('validate_html', True),
            'no-validate-html': ('validate_html', False),
            'disallow-orphan-blocks': ('disallow_orphan_blocks', True),
            'no-disallow-orphan-blocks': ('disallow_orphan_blocks', False),
        }

        if value in actions:
            setattr(self, actions[value][0], actions[value][1])
        else:
            if node:
                raise CompileException(node, 'No such template preprocessor option: %s' % value)
            else:
                raise CompileException('No such template preprocessor option: %s (in settings.py)' % value)

