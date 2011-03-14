from django.utils import translation
from django.conf import settings
from django.template import TemplateDoesNotExist

import os
import codecs

EXCLUDED_APPS = [ 'debug_toolbar', 'django_extensions' ]

def language(lang):
    """
    Execute the content of this block in the language of the user.
    To be used as follows:

    with language(lang):
       some_thing_in_this_language()

    """
    class with_block(object):
        def __enter__(self):
            self._old_language = translation.get_language()
            translation.activate(lang)

        def __exit__(self, *args):
            translation.activate(self._old_language)

    return with_block()


def _get_path_form_app(app):
    m = __import__(app)
    if '.' in app:
        parts = app.split('.')
        for p in parts[1:]:
            m = getattr(m, p)
    return m.__path__[0]


def template_iterator():
    """
    Iterate through all templates of all installed apps.
    (Except EXCLUDED_APPS)
    """
    def walk(directory):
        for root, dirs, files in os.walk(directory):
            for f in files:
                if not os.path.normpath(os.path.join(root, f)).startswith(settings.TEMPLATE_CACHE_DIR):
                    if f.endswith('.html'):
                        yield os.path.relpath(os.path.join(root, f), directory)

    for dir in settings.TEMPLATE_DIRS:
        for f in walk(dir):
            yield dir, f

    for app in settings.INSTALLED_APPS:
        if app not in EXCLUDED_APPS:
            dir = os.path.join(_get_path_form_app(app), 'templates')
            for f in walk(dir):
                yield dir, f

def load_template_source(path):
    """
    Look in the template loaders for this template, return content.
    """
    for dir in settings.TEMPLATE_DIRS:
        p = os.path.join(dir, path)
        if os.path.exists(p):
            return codecs.open(p, 'r', 'utf-8').read()

    for app in settings.INSTALLED_APPS:
        p = os.path.join(_get_path_form_app(app), 'templates', path)
        if os.path.exists(p):
            return codecs.open(p, 'r', 'utf-8').read()

    raise TemplateDoesNotExist, path
