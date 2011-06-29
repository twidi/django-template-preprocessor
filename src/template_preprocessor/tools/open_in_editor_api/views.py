from django.http import HttpResponse
from template_preprocessor.utils import get_template_path

import subprocess


def open_in_editor(request):
    from django.conf import settings

    template = request.REQUEST['template']

    # Get template path
    path = get_template_path(template)
    print 'opening template: ' + path

    # Call command for opening this file
    if hasattr(settings, 'TEMPLATE_PREPROCESSOR_OPEN_IN_EDITOR_COMMAND'):
        settings.TEMPLATE_PREPROCESSOR_OPEN_IN_EDITOR_COMMAND(path)
    else:
        subprocess.Popen(["/usr/bin/gvim", "--remote-tab", path ])

    return HttpResponse('[{ "result": "ok" }]', mimetype="application/javascript")
