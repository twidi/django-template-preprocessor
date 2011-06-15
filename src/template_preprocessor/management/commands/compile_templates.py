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
from template_preprocessor.core.lexer import CompileException

from template_preprocessor.utils import language, template_iterator, load_template_source, get_template_path
from template_preprocessor.utils import get_options_for_path, execute_precompile_command
from template_preprocessor.core.utils import need_to_be_recompiled, create_media_output_path
from template_preprocessor.core.context import Context


class Command(BaseCommand):
    help = "Preprocess all the templates form all known applications."
    option_list = BaseCommand.option_list + (
        make_option('--language', action='append', dest='languages', help='Give the languages'),
        make_option('--all', action='store_true', dest='all_templates', help='Compile all templates (instead of only the changed)'),
        make_option('--boring', action='store_true', dest='boring', help='No colors in output'),
        make_option('--noinput', action='store_false', dest='interactive', default=True,
                        help='Tell Django to NOT prompt the user for input of any kind.'),
    )


    def __init__(self, *args, **kwargs):
        class NiceContext(Context):
            """
            Same as the real context class, but override some methods in order to gain
            nice colored output.
            """
            def compile_media_callback(s, compress_tag, media_files):
                """
                When the compiler notifies us that compiling of this file begins.
                """
                if compress_tag:
                    print self.colored('Compiling media files from', 'yellow'),
                    print self.colored(' "%s" ' % compress_tag.path, 'green'),
                    print self.colored(' (line %s, column %s)" ' % (compress_tag.line, compress_tag.column), 'yellow')
                else:
                    print self.colored('Compiling media files', 'yellow')

                for m in media_files:
                    print self.colored('   * %s' % m, 'green')

            def compile_media_progress_callback(s, compress_tag, media_file, current, total):
                """
                Print progress of compiling media files.
                """
                print self.colored('       (%s / %s):' % (current, total), 'yellow'),
                print self.colored(' %s' % (media_file), 'green')
        self.NiceContext = NiceContext

        BaseCommand.__init__(self, *args, **kwargs)


    def print_error(self, text):
        self._errors.append(text)
        print self.colored(text, 'white', 'on_red').encode('utf-8')


    def colored(self, text, *args, **kwargs):
        if self.boring:
            return text
        else:
            return termcolor.colored(text, *args, **kwargs)

    def handle(self, *args, **options):
        all_templates = options['all_templates']
        interactive = options['interactive']

        # Default verbosity
        self.verbosity = int(options.get('verbosity', 1))

        # Colors?
        self.boring = bool(options.get('boring'))

        # All languages by default
        languages = [l[0] for l in settings.LANGUAGES]
        if options['languages'] is None:
            options['languages'] = languages


        self._errors = []
        if languages.sort() != options['languages'].sort():
            print self.colored('Warning: all template languages are deleted while we won\'t generate them again.',
                                    'white', 'on_red')

        # Delete previously compiled templates and media files
        # (This is to be sure that no template loaders were configured to
        # load files from this cache.)
        if all_templates:
            if not interactive or raw_input('\nDelete all files in template cache directory: %s? [y/N] ' %
                                settings.TEMPLATE_CACHE_DIR).lower() == 'y':
                for root, dirs, files in os.walk(settings.TEMPLATE_CACHE_DIR):
                    for f in files:
                        if not f[0] == '.': # Skip hidden files
                            path = os.path.join(root, f)
                            if self.verbosity >= 1:
                                print ('Deleting old template: %s' % path)
                            os.remove(path)

            if not interactive or raw_input('\nDelete all files in media cache directory %s? [y/N] ' %
                                settings.MEDIA_CACHE_DIR).lower() == 'y':
                for root, dirs, files in os.walk(settings.MEDIA_CACHE_DIR):
                    for f in files:
                        if not f[0] == '.': # Skip hidden files
                            path = os.path.join(root, f)
                            if self.verbosity >= 1:
                                print ('Deleting old media file: %s' % path)
                            os.remove(path)

        # Build compile queue
        queue = self._build_compile_queue(options['languages'], all_templates)

        # Precompile command
        execute_precompile_command()

        # Compile queue
        for i in range(0, len(queue)):
            lang = queue[i][0]
            with language(lang):
                if self.verbosity >= 2:
                    print self.colored('%i / %i |' % (i+1, len(queue)), 'yellow'),
                    print self.colored('(%s)' % lang, 'yellow'),
                    print self.colored(queue[i][1], 'green')

                self._compile_template(*queue[i])

        # Show all errors once again.
        print u'\n*** %i Files processed, %i compile errors ***' % (len(queue), len(self._errors))

        # Build media compile queue
        media_queue = self._build_compile_media_queue(options['languages'])

        # Compile media queue
        self._errors = []
        for i in range(0, len(media_queue)):
            lang = media_queue[i][0]
            with language(lang):
                if self.verbosity >= 2:
                    print self.colored('%i / %i |' % (i+1, len(media_queue)), 'yellow'),
                    print self.colored('(%s)' % lang, 'yellow'),
                    print self.colored(','.join(media_queue[i][1]), 'green')
                self._compile_media(*media_queue[i])

        # Show all errors once again.
        print u'\n*** %i Media files processed, %i compile errors ***' % (len(media_queue), len(self._errors))

        # Ring bell :)
        print '\x07'


    def _build_compile_queue(self, languages, all_templates=True):
        """
        Build a list of all the templates to be compiled.
        """
        # Create compile queue
        queue = set() # Use a set, avoid duplication of records.

        if self.verbosity >= 2:
            print 'Building queue'

        for lang in languages:
            # Now compile all templates to the cache directory
            for dir, t in template_iterator():
                input_path = os.path.join(dir, t)
                output_path = self._make_output_path(lang, t)

                # Compile this template if:
                if (
                        # We are compiling *everything*
                        all_templates or

                        # Compiled file does not exist
                        not os.path.exists(output_path) or

                        # Compiled file has been marked for recompilation
                        os.path.exists(output_path + '-c-recompile') or

                        # Compiled file is outdated
                        os.path.getmtime(output_path) < os.path.getmtime(input_path)):

                    queue.add( (lang, t, input_path, output_path) )

                    # When this file has to be compiled, and other files depend
                    # on this template also compile the other templates.
                    if os.path.exists(output_path + '-c-used-by'):
                        for t2 in open(output_path + '-c-used-by', 'r').read().split('\n'):
                            if t2:
                                try:
                                    queue.add( (lang, t2, get_template_path(t2), self._make_output_path(lang, t2)) )
                                except TemplateDoesNotExist, e:
                                    pass # Reference to non-existing template

        queue = list(queue)
        queue.sort()
        return queue


    def _build_compile_media_queue(self, languages):
        from template_preprocessor.core.utils import compile_external_css_files, compile_external_javascript_files

        queue = []
        for root, dirs, files in os.walk(settings.MEDIA_CACHE_DIR):
            for f in files:
                if f.endswith('-c-meta'):
                    input_files = open(os.path.join(root, f), 'r').read().split('\n')
                    output_file = f[:-len('-c-meta')]
                    lang = os.path.split(root)[-1]

                    if output_file.endswith('.js'):
                        extension = 'js'
                        compiler = compile_external_javascript_files
                    elif output_file.endswith('.css'):
                        extension = 'css'
                        compiler = compile_external_css_files
                    else:
                        extension = None

                    if extension and need_to_be_recompiled(input_files, create_media_output_path(input_files, extension, lang)):
                        queue.append((lang, input_files, compiler))

        queue.sort()
        return queue


    def _compile_media(self, lang, input_urls, compiler):
        context = self.NiceContext('External media: ' + ','.join(input_urls))
        compiler(input_urls, context)


    def _make_output_path(self, language, template):
        return os.path.join(settings.TEMPLATE_CACHE_DIR, language, template)


    def _save_template_dependencies(self, lang, template, dependency_list):
        """
        Store template dependencies into meta files.  (So that we now which
        templates need to be recompiled when one of the others has been
        changed.)
        """
        # Reverse dependencies
        for t in dependency_list:
            output_path = self._make_output_path(lang, t) + '-c-used-by'
            self._create_dir(os.path.split(output_path)[0])

            # Append current template to this list if it doesn't appear yet
            deps = open(output_path, 'r').read().split('\n') if os.path.exists(output_path) else []

            if not template in deps:
                open(output_path, 'a').write(template + '\n')

        # Dependencies
        output_path = self._make_output_path(lang, template) + '-c-depends-on'
        open(output_path, 'w').write('\n'.join(dependency_list) + '\n')

    def _save_first_level_template_dependencies(self, lang, template, include_list, extends_list):
        """
        First level dependencies (used for generating dependecy graphs)
        (This doesn't contain the indirect dependencies.)
        """
        # {% include "..." %}
        output_path = self._make_output_path(lang, template) + '-c-includes'
        open(output_path, 'w').write('\n'.join(include_list) + '\n')

        # {% extends "..." %}
        output_path = self._make_output_path(lang, template) + '-c-extends'
        open(output_path, 'w').write('\n'.join(extends_list) + '\n')

    def _compile_template(self, lang, template, input_path, output_path, no_html=False):
        try:
            # Create output directory
            self._create_dir(os.path.split(output_path)[0])

            try:
                # Open input file
                code = codecs.open(input_path, 'r', 'utf-8').read()
            except UnicodeDecodeError, e:
                raise CompileException(0, 0, input_path, str(e))

            # Compile
            if no_html:
                output, context = compile(code, path=input_path, loader=load_template_source,
                            options=get_options_for_path(input_path) + ['no-html'],
                            context_class=self.NiceContext)
            else:
                output, context = compile(code, path=input_path, loader=load_template_source,
                            options=get_options_for_path(input_path),
                            context_class=self.NiceContext)

            # store dependencies
            self._save_template_dependencies(lang, template, context.template_dependencies)
            self._save_first_level_template_dependencies(lang, template, context.include_dependencies,
                                                                context.extends_dependencies)

            # Open output file
            codecs.open(output_path, 'w', 'utf-8').write(output)

            # Delete -c-recompile file (mark for recompilation) if one such exist.
            if os.path.exists(output_path + '-c-recompile'):
                os.remove(output_path + '-c-recompile')

            return True

        except CompileException, e:
            # Try again without html
            if not no_html:
                # Print the error
                self.print_error(u'ERROR:  %s' % unicode(e))

                print u'Trying again with option "no-html"... ',
                if self._compile_template(lang, template, input_path, output_path, no_html=True):
                    print 'Succeeded'
                else:
                    print 'Failed again'

                # Create recompile mark
                open(output_path + '-c-recompile', 'w').close()

        except TemplateDoesNotExist, e:
            if self.verbosity >= 2:
                print u'WARNING: Template does not exist:  %s' % unicode(e)

    def _create_dir(self, newdir):
        if not os.path.isdir(newdir):
            os.makedirs(newdir)

