#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Django template preprocessor.
Author: Jonathan Slenders, City Live
"""
from template_preprocessor.core.lexer import CompileException
import os

from template_preprocessor.core.utils import compile_external_javascript_files, compile_external_css_files


class GettextEntry(object):
    def __init__(self, path, line, column, text):
        self.path = path
        self.line = line
        self.column = column
        self.text = text

    def __unicode__(self):
        return "%s (line %s, column %s)" % (node.path, node.line, node.column)



class Context(object):
    """
    Preprocess context. Contains the compile settings, error logging,
    remembers dependencies, etc...
    """
    def __init__(self, path, loader=None, extra_options=None):
        self.loader = loader

        # Remember stuff
        self.warnings = []
        self.media_dependencies = []
        self.gettext_entries = []

        # template_dependencies: will contains all other templates which are
        # needed for compilation of this template.
        self.template_dependencies = []

        # Only direct dependencies (first level {% include %} and {% extends %})
        self.include_dependencies = []
        self.extends_dependencies = []

        # Process options
        self.options = Options()
        for o in extra_options or []:
            self.options.change(o)

    def compile_media_calback(self, compress_tag, media_files):
        """
        Callback for the media compiler. Override for different output.
        """
        print 'Compiling media files from "%s" (line %s, column %s)' % \
                        (compress_tag.path, compress_tag.line, compress_tag.column)
        print ', '.join(media_files)

    def compile_media_progress_callback(self, compress_tag, media_file, current, total):
        """
        Print progress of compiling media files.
        """
        print ' (%s / %s): %s' % (current, total, media_file)

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

    def remember_gettext(self, node, text):
        self.gettext_entries.append(GettextEntry(node.path, node.line, node.column, text))

    def remember_include(self, template):
        self.include_dependencies.append(template)

    def remember_extends(self, template):
        self.extends_dependencies.append(template)

    # What to do with media files

    def compile_js_files(self, compress_tag, media_files):
        return compile_external_javascript_files(media_files, self, compress_tag)

    def compile_css_files(self, compress_tag, media_files):
        return compile_external_css_files(media_files, self, compress_tag)



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
        self.execute_preprocessable_tags = True
        self.merge_all_load_tags = True
        self.preprocess_ifdebug = True # Should probably always be True
        self.preprocess_macros = True
        self.preprocess_translations = True
        self.preprocess_urls = True
        self.preprocess_variables = True
        self.remove_block_tags = True # Should propably not be disabled
        self.remove_some_tags = True # As we lack a better settings name
        self.whitespace_compression = True

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
            'compile-css': ('compile_css', True),
            'compile-javascript': ('compile_javascript', True),
            'disallow-orphan-blocks': ('disallow_orphan_blocks', True),
            'html': ('is_html', True), # Enable HTML extensions
            'html-remove-empty-class-attributes': ('remove_empty_class_attributes', True),
            'merge-internal-css': ('merge_internal_css', True),
            'merge-internal-javascript': ('merge_internal_javascript', True),
            'no-disallow-orphan-blocks': ('disallow_orphan_blocks', False),
            'no-html': ('is_html', False), # Disable all HTML specific options
            'no-i18n-preprocessing': ('preprocess_translations', False),
            'no-macro-preprocessing': ('preprocess_macros', False),
            'no-pack-external-css': ('pack_external_css', False),
            'no-pack-external-javascript': ('pack_external_javascript', False),
            'no-validate-html': ('validate_html', False),
            'no-whitespace-compression': ('whitespace_compression', False),
            'pack-external-css': ('pack_external_css', True),
            'pack-external-javascript': ('pack_external_javascript', True),
            'validate-html': ('validate_html', True),
            'whitespace-compression': ('whitespace_compression', True),
        }

        if value in actions:
            setattr(self, actions[value][0], actions[value][1])
        else:
            if node:
                raise CompileException(node, 'No such template preprocessor option: %s' % value)
            else:
                raise CompileException('No such template preprocessor option: %s (in settings.py)' % value)

