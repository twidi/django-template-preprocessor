from django.http import HttpResponse
from template_preprocessor.utils import get_template_path

import subprocess
import time


def open_in_editor(request):
    from django.conf import settings

    template = request.REQUEST['template']
    line = request.REQUEST.get('line', 0)
    column = request.REQUEST.get('column', 0)

    # Get template path
    path = get_template_path(template)
    print 'opening template: ' + path

    # Call command for opening this file
    if hasattr(settings, 'TEMPLATE_PREPROCESSOR_OPEN_IN_EDITOR_COMMAND'):
        settings.TEMPLATE_PREPROCESSOR_OPEN_IN_EDITOR_COMMAND(path, line, column)
    else:
        # By default, open this file in GVim, in a new tab.
        subprocess.Popen(["/usr/bin/gvim"])
        #subprocess.Popen(["/usr/bin/gvim", "--remote-tab", path ])
        time.sleep(0.4)
        subprocess.Popen(["/usr/bin/gvim", "--remote-send", "<ESC>:tabe %s<ENTER>" % path ])
        subprocess.Popen(["/usr/bin/gvim", "--remote-send", "<ESC>:%s<ENTER>%s|" % (line, column)])

    return HttpResponse('[{ "result": "ok" }]', mimetype="application/javascript")
