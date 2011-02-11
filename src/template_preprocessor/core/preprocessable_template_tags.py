
from django.conf import settings
from django.utils.translation import ugettext as _

import re


class NotPreprocessable(Exception):
    pass


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

def _tab_content(*args):
    return (u'<div class="tabbing-loader" style="display:none;">'
                u'<img src="%scommon/img/loader.gif" alt="" /> %s</div>'
                u'<div class="tabbing-content">') % (settings.MEDIA_URL, _('Loading data...'))



PREPROCESS_TAGS = {
    'google_analytics': _google_analytics,
    'now': _now,

    # Tab pages -> default style
    'tabpage': lambda *args: u'<div class="tabbing">',
        'tabs': lambda *args: u'<div class="tabbing-tabs">',
        'endtabs': lambda *args: u'</div>',
        'tabcontent': _tab_content,
        'endtabcontent': lambda *args: u'</div>',
    'endtabpage': lambda *args: u'</div>',
    }
