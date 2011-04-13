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

def get_template_path(template):
    """
    Turn template path into absolute path
    """
    for dir in settings.TEMPLATE_DIRS:
        p = os.path.join(dir, template)
        if os.path.exists(p):
            return p

    for app in settings.INSTALLED_APPS:
        p = os.path.join(_get_path_form_app(app), 'templates', template)
        if os.path.exists(p):
            return p

    raise TemplateDoesNotExist, template


def load_template_source(template):
    """
    Get template source code.
    """
    path = get_template_path(template)
    return codecs.open(path, 'r', 'utf-8').read()


def get_options_for_path(path):
    """
    return a list of default settings for this template.
    (find app, and return settings for the matching app.)
    """
    result = []
    for app in settings.INSTALLED_APPS:
        dir = os.path.normpath(os.path.join(_get_path_form_app(app), 'templates')).lower()
        if os.path.normpath(path).lower().startswith(dir):
            result = get_options_for_app(app)

        # NOTE: somehow, we get lowercase paths from the template origin in
        # Windows, so convert both paths to lowercase before comparing.

    # Disable all HTML extensions if the template name does not end with .html
    # (Can still be overriden in the templates.)
    if path and not path.endswith('.html'):
        result = list(result) + ['no-html']

    return result


def get_options_for_app(app):
    """
    return a list of default settings for this application.
    (e.g. Some applications, like the django admin are not HTML compliant with
    this validator.)

    -- settings.py --
    TEMPLATE_PREPROCESSOR_OPTIONS = {
            # Default
            '*', ('html',),
            ('django.contrib.admin', 'django.contrib.admindocs', 'debug_toolbar'): ('no-html',),
    }
    """
    # Read settings.py
    options = getattr(settings, 'TEMPLATE_PREPROCESSOR_OPTIONS', { })
    result = []

    # Possible fallback: '*'
    if '*' in options:
        result += list(options['*'])

    # Look for any configuration entry which contains this appname
    for k, v in options.iteritems():
        if app == k or app in k:
            if isinstance(v, tuple):
                result += list(v)
            else:
                raise Exception('Configuration error in settings.TEMPLATE_PREPROCESSOR_OPTIONS')

    return result
