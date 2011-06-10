"""
Author: Jonathan Slenders, City Live
"""
import os
import codecs
from optparse import make_option
import termcolor

from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.urlresolvers import reverse
from django.template import TemplateDoesNotExist

from template_preprocessor.core import compile
from template_preprocessor.core import compile_to_parse_tree
from template_preprocessor.core.lexer import CompileException

from template_preprocessor.utils import language, template_iterator, load_template_source
from template_preprocessor.core.django_processor import parse, DjangoTransTag, DjangoBlocktransTag


IGNORE_WORDS = [

]


class Command(BaseCommand):
    help = "Spellcheck all templates."

    def found_spelling_errors(self, tag, word):
        if not word in self._errors:
            self._errors[word] = 1
        else:
            self._errors[word] += 1

        print '     ', termcolor.colored(word.strip().encode('utf-8'), 'white', 'on_red'),
        print '(%s, Line %s, column %s)' % (tag.path, tag.line, tag.column)


    def handle(self, *args, **options):
        self._errors = []

        # Default verbosity
        self.verbosity = int(options.get('verbosity', 1))

        # Now compile all templates to the cache directory
        for dir, t in template_iterator():
            input_path = os.path.join(dir, t)
            self._spellcheck(input_path)

        # Show all errors once again.
        print u'\n*** %i spelling errors ***' % len(self._errors)

        # Ring bell :)
        print '\x07'

    def _spellcheck(self, input_path):
        # Now compile all templates to the cache directory
            try:
                print termcolor.colored(input_path, 'green')

                # Open input file
                code = codecs.open(input_path, 'r', 'utf-8').read()

                # Compile
                tree = compile_to_parse_tree(code, loader=load_template_source, path=input_path)

                # For every text node
                for tag in tree.child_nodes_of_class([DjangoTransTag, DjangoBlocktransTag, ]):
                    if isinstance(tag, DjangoTransTag):
                        self._check_sentence(f, tag, tag.string)

                    if isinstance(tag, DjangoBlocktransTag):
                        for t in tag.children:
                            if isinstance(t, basestring):
                                self._check_sentence(f, tag, t)

            except CompileException, e:
                self.print_warning(u'Warning:  %s' % unicode(e))

            except TemplateDoesNotExist, e:
                self.print_warning(u'Template does not exist: %s' % unicode(e))

    def _check_sentence(self, path, tag, sentence):
        import subprocess
        p = subprocess.Popen(['aspell', '-l', 'en', 'list'], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        p.stdin.write(sentence.encode('utf-8'))
        output = p.communicate()[0]
        for o in output.split():
            o = o.strip()
            if not (o in IGNORE_WORDS or o.lower() in IGNORE_WORDS):
                self.found_spelling_errors(tag, o)

