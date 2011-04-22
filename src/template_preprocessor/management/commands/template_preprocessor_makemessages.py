"""
Author: Jonathan Slenders, City Live
"""
import os
import sys
import codecs
from optparse import make_option
import termcolor

from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.urlresolvers import reverse
from django.template import TemplateDoesNotExist

from template_preprocessor.core import compile
from template_preprocessor.core.lexer import CompileException

from template_preprocessor.utils import language, template_iterator, load_template_source, get_template_path
from template_preprocessor.utils import get_options_for_path



class Command(BaseCommand):
    help = "Print all strings found in the templates and javascript gettext(...)"


    def handle(self, *args, **options):
        # Default verbosity
        self.verbosity = int(options.get('verbosity', 1))

        self.strings = { } # Maps msgid -> list of paths

        # Build queue
        queue = set()
        print 'Building queue'

        # Build list of all templates
        for dir, t in template_iterator():
            input_path = os.path.join(dir, t)
            queue.add( (t, input_path) )

        queue = list(queue)
        queue.sort()

        # Process queue
        for i in range(0, len(queue)):
            if self.verbosity >= 2:
                sys.stderr.write(termcolor.colored('%i / %i |' % (i, len(queue)), 'yellow'))
                sys.stderr.write(termcolor.colored(queue[i][1], 'green'))
            self.process_template(*queue[i])

        # Output string to stdout
        for s in self.strings:
            for l in self.strings[s]:
                print l
            print 'msgid "%s"' % s.replace('"', r'\"')
            print 'msgstr ""'
            print


    def process_template(self, template, input_path):
        # TODO: when HTML processing fails, the 'context' attribute is not
        #       retreived and no translations are failed.  so, translate again
        #       without html. (But we need to process html, in order to find
        #       gettext() in javascript.)

        try:
            try:
                # Open input file
                code = codecs.open(input_path, 'r', 'utf-8').read()
            except UnicodeDecodeError, e:
                raise CompileException(0, 0, input_path, str(e))

            # Compile
            output, context = compile(code, path=input_path, loader=load_template_source,
                        options=get_options_for_path(input_path))

            for entry in context.gettext_entries:
                line = '#: %s:%s:%s' % (entry.path, entry.line, entry.column)

                if not entry.text in self.strings:
                    self.strings[entry.text] = set()

                self.strings[entry.text].add(line)

                if self.verbosity >= 2:
                    sys.stderr.write(line + '\n')
                    sys.stderr.write('msgid "%s"\n\n' % entry.text.replace('"', r'\"'))

        except CompileException, e:
            sys.stderr.write(termcolor.colored('Warning: failed to process %s: \n%s\n' % (input_path, e),
                                    'white', 'on_red'))

        except TemplateDoesNotExist, e:
            pass
