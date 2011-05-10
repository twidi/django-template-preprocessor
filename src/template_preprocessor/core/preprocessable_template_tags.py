
from django.conf import settings
from django.utils.translation import ugettext as _

import re

__doc__ = """
Extensions to the preprocessor, if certain tags are possible to be preprocessed,
you can add these in your application as follows:

from template_preprocessor import preproces_tag

@preprocess_tag
def now(*args):
    if len(args) == 2 and args[1] in (u'"Y"', u"'Y'"):
        import datetime
        return unicode(datetime.datetime.now().year)
    else:
        raise NotPreprocessable()

"""


class NotPreprocessable(Exception):
    """
    Raise this exception when a template tag which has been registered as being
    preprocessable, can not be preprocessed with the current arguments.
    """
    pass


# === Discover preprocessable tags

__preprocessabel_tags = { }

def preprocess_tag(func_or_name):
    """
    > @preprocess_tag
    > def my_template_tag(*args):
    >     return '<p>.....</p>'

    > @preprocess_tag('my_template_tag')
    > def func(*args):
    >     return '<p>.....</p>'
    """
    if isinstance(func_or_name, basestring):
        def decorator(func):
            __preprocessabel_tags[func_or_name] = func
            return func
        return decorator
    else:
        __preprocessabel_tags[func_or_name.__name__] = func_or_name
        return func_or_name


def discover_template_tags():
    for a in settings.INSTALLED_APPS:
        try:
            __import__('%s.preprocessable_template_tags' % a)
        except ImportError, e:
            pass



_discovered = False

def get_preprocessable_tags():
    global _discovered

    if not _discovered:
        discover_template_tags()
        _discovered = True

    return __preprocessabel_tags



# ==== Build-in preprocessable tags ====


@preprocess_tag('google_analytics')
def _google_analytics(*args):
    if len(args) != 1: raise NotPreprocessable()

    return re.compile('\s\s+').sub(' ',  '''
    <script type="text/javascript">
        var gaJsHost = (("https:" == document.location.protocol) ? "https://ssl." : "http://www.");
        document.write(unescape("%%3Cscript src='" + gaJsHost + "google-analytics.com/ga.js' type='text/javascript'%%3E%%3C/script%%3E"));
    </script>
    <script type="text/javascript">
        try {
            var pageTracker = _gat._getTracker("%s");
            pageTracker._trackPageview();
        } catch(err) {}
    </script>
    ''' % getattr(settings, 'URCHIN_ID', None))


@preprocess_tag('now')
def _now(*args):
    """
    The output of the following template tag will probably not change between
    reboots of the django server.
    {% now "Y" %}
    """
    if len(args) == 2 and args[1] in (u'"Y"', u"'Y'"):
        import datetime
        return unicode(datetime.datetime.now().year)
    else:
        raise NotPreprocessable()

