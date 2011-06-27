# Author: Jonathan Slenders, City Live

# Template loaders

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.template import TemplateDoesNotExist
from django.template.loader import BaseLoader, get_template_from_string, find_template_loader, make_origin
from django.utils import translation
from django.utils.hashcompat import sha_constructor
from django.utils.importlib import import_module
from django.template import StringOrigin

from template_preprocessor.core import compile
from template_preprocessor.core.context import Context
from template_preprocessor.utils import get_options_for_path, execute_precompile_command

import os
import codecs


# Override this compiler options for following template loaders
_OVERRIDE_OPTIONS_FOR_VALIDATION = [
        # No processing of external media, this quickly becomes too slow to
        # do in real time for a lot of media.
        'no-pack-external-css',
        'no-pack-external-javascript'
        ]

_OVERRIDE_OPTIONS_AT_RUNTIME_PROCESSED = [
        'no-pack-external-css',
        'no-pack-external-javascript'
        ]
_OVERRIDE_OPTIONS_AT_DEBUG = [
        'no-pack-external-css',
        'no-pack-external-javascript',
        'no-whitespace-compression'
        ]


class _Base(BaseLoader):
    is_usable = True

    def __init__(self, loaders):
        self._loaders = loaders
        self._cached_loaders = []

    @property
    def loaders(self):
        # Resolve loaders on demand to avoid circular imports
        if not self._cached_loaders:
            for loader in self._loaders:
                self._cached_loaders.append(find_template_loader(loader))
        return self._cached_loaders

    def find_template(self, name, dirs=None):
        for loader in self.loaders:
            try:
                template, display_name = loader.load_template_source(name, dirs)
                return (template, make_origin(display_name, loader.load_template_source, name, dirs))
            except TemplateDoesNotExist, e:
                pass
            except NotImplementedError, e:
                raise Exception('Template loader %s does not implement load_template_source. Be sure not to nest '
                            'loaders which return only Template objects into the template preprocessor. (We need '
                            'a loader which returns a template string.)' % unicode(loader))
        raise TemplateDoesNotExist(name)


class PreprocessedLoader(_Base):
    """
    Use preprocessed templates.
    If no precompiled version is available, use the original version, but don't compile at runtime.
    """
    __cache_dir = settings.TEMPLATE_CACHE_DIR

    def __init__(self, loaders):
        _Base.__init__(self, loaders)
        self.template_cache = {}

    def load_template(self, template_name, template_dirs=None):
        lang = translation.get_language() or 'en'
        key = '%s-%s' % (lang, template_name)

        if key not in self.template_cache:
            # Path in the cache directory
            output_path = os.path.join(self.__cache_dir, lang, template_name)

            # Load template
            if os.path.exists(output_path):
                # Prefer precompiled version
                template = codecs.open(output_path, 'r', 'utf-8').read()
                origin = StringOrigin(template)
            else:
                template, origin = self.find_template(template_name, template_dirs)

                # Compile template (we shouldn't compile anything at runtime.)
                #template, context = compile(template, loader = lambda path: self.find_template(path)[0], path=template_name)

            # Turn into Template object
            template = get_template_from_string(template, origin, template_name)

            # Save in cache
            self.template_cache[key] = template

        # Return result
        return self.template_cache[key], None


    def reset(self):
        "Empty the template cache."
        self.template_cache.clear()


class RuntimeProcessedLoader(_Base):
    """
    Load templates through the preprocessor. Compile at runtime.
    """
    context_class = Context
    options = _OVERRIDE_OPTIONS_AT_RUNTIME_PROCESSED

    def load_template(self, template_name, template_dirs=None):
        template, origin = self.find_template(template_name, template_dirs)

        # Precompile command
        execute_precompile_command()
        print 'compiling %s' % template_name

        # Compile template
        template, context = compile(template, path=template_name, loader = lambda path: self.find_template(path)[0],
                        options=get_options_for_path(origin.name) + self.options,
                        context_class=self.context_class)

        # Turn into Template object
        template = get_template_from_string(template, origin, template_name)

        # Return result
        return template, None

context_cache = {} # TODO

class DebugLoader(RuntimeProcessedLoader):
    """
    Load templates through the preprocessor. Does validation, compiles and inserts
    debug symbol. (For use with browser extensions.)
    """
    class context_class(Context):
        def __init__(self, *args, **kwargs):
            kwargs['insert_debug_symbols'] = True
            Context.__init__(self, *args, **kwargs)

    options = _OVERRIDE_OPTIONS_AT_DEBUG

    def load_template(self, *args, **kwargs):
        template, origin = RuntimeProcessedLoader.load_template(self, *args, **kwargs)

        # Wrap Template.render by a method which stores the render context in
        # the cache. (So we can have a webpage automatically render itself
        # when one of the source files has been changed, through javascript.)
        original_render = template.render
        def new_render(context):
            if not 'template_preprocessor_context_id' in context:
                context['template_preprocessor_context_id'] = self._store_context(context)
            return original_render(context)
        template.render = new_render

        return template, origin

    def _store_context(self, context):
        """
        Store this context in the case, and return it's unique id.
        """
        #from django.core.cache import cache

        # TODO: Not yet using the real cache. We need
        # to build a proxy around context, capture every get call, and
        # meanwhile build a similar dict/list to be used for next rendering call.

        import random, string
        alphabet = string.ascii_letters
        key = ''.join([alphabet[random.randint(0, len(string.ascii_letters) - 1)] for __ in range(0, 32)])

        #cache.set('tp-context-cache-%s' % key, context)
        context_cache['tp-context-cache-%s' % key] = context
        return key

class ValidatorLoader(_Base):
    """
    Wrapper for validating templates through the preprocessor. For Django 1.2
    It will compile the templates as a test and possibly raises CompileException
    when it fails to. But it still returns a Template object of the original
    template, without any caching.
    """
    def load_template(self, template_name, template_dirs=None):
        # IMPORTANT NOTE:  We load the template, using the original loaders.
        #                  call compile, but still return the original,
        #                  unmodified result.  This causes the django to call
        #                  load_template again for every include node where of
        #                  course the validation may fail. (incomplete HTML
        #                  tree, maybe only javascript, etc...)
        # Load template
        template, origin = self.find_template(template_name, template_dirs)

        # Compile template as a test (could raise CompileException), throw away the compiled result.
        try:
            # Don't compile template when a parent frame was a 'render' method. Than it's probably a
            # runtime call from an IncludeNode or ExtendsNode.
            import inspect
            if not any(i[3] in ('render', 'do_include') for i in inspect.getouterframes(inspect.currentframe())):
                # Precompile command
                print 'compiling %s' % template_name
                execute_precompile_command()

                compile(template, loader = lambda path: self.find_template(path)[0], path=template_name,
                            options=get_options_for_path(origin.name) + _OVERRIDE_OPTIONS_FOR_VALIDATION )

        except Exception, e:
            # Print exception on console
            print '---'
            print 'Template: %s' % template_name
            print e
            print '-'
            import traceback
            traceback.print_exc()
            print '---'
            raise e

        # Turn into Template object
        template = get_template_from_string(template, origin, template_name)

        # Return template
        return template, None
