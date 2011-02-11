"""
Wrapper for loading the optimized, compiled templates. For Django 1.2
"""


from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.template import TemplateDoesNotExist
from django.template.loader import BaseLoader, get_template_from_string, find_template_loader, make_origin
from django.utils import translation
from django.utils.hashcompat import sha_constructor
from django.utils.importlib import import_module
from django.template import StringOrigin
from template_preprocessor.render_engine.render import compile_tree, Template
from template_preprocessor.core import compile_to_parse_tree

from template_preprocessor.core import compile

import os
import codecs



"""
Use this loader to experiment with running the to-python-compiled templates.
Implementation is probably like 75% finished.
"""


class Loader(BaseLoader):
    is_usable = True
    __cache_dir = settings.TEMPLATE_CACHE_DIR

    def __init__(self, loaders):
        self.template_cache = {}
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
            except TemplateDoesNotExist:
                pass
            except NotImplementedError, e:
                raise Exception('Template loader %s does not implement load_template_source. Be sure not to nest '
                            'loaders which return only Template objects into the template preprocessor. (We need '
                            'a loader which returns a template string.)' % unicode(loader))
        raise TemplateDoesNotExist(name)

    def load_template(self, template_name, template_dirs=None):
        lang = translation.get_language() or 'en'
        key = '%s-%s' % (lang, template_name)

        if key not in self.template_cache:
            # Path in the cache directory
            output_path = os.path.join(self.__cache_dir, 'cache', lang, template_name)

            # Load template
            if os.path.exists(output_path):
                # Prefer precompiled version
                template = codecs.open(output_path, 'r', 'utf-8').read()
                origin = StringOrigin(template)
            else:
                template, origin = self.find_template(template_name, template_dirs)

            # Compile template
            output = compile_to_parse_tree(template, loader = lambda path: self.find_template(path)[0], path=template_name)

            # Compile to python
            output2 = compile_tree(output)
            template = Template(output2, template_name)

            # Turn into Template object
            #template = get_template_from_string(template, origin, template_name)

            # Save in cache
            self.template_cache[key] = template

        # Return result
        return self.template_cache[key], None

    def reset(self):
        "Empty the template cache."
        self.template_cache.clear()
