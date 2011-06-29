from django.core.management.base import BaseCommand, CommandError
from optparse import make_option
import os
import sys


class Command(BaseCommand):
    help = "Server for opening Django templates in your code editor. (Used by the chromium extension)"

    """
    The Chromium extension for browsing the Django Template Source code runs
    in a sandbox, and is not able to execute native commands. The extension
    can however do HTTP requests to this server on 'localhost' which can in
    turn execute the system command for opening the editor.
    """
    def handle(self, addrport='', *args, **options):
        import django
        from django.core.servers.basehttp import run, AdminMediaHandler, WSGIServerException
        from django.core.handlers.wsgi import WSGIHandler

        if args:
            raise CommandError('Usage is runserver %s' % self.args)
        if not addrport:
            addr = ''
            port = 8900
        else:
            try:
                addr, port = addrport.split(':')
            except ValueError:
                addr, port = '', addrport
        if not addr:
            addr = '127.0.0.1'

        # Patch the settings
        def patch_settings():
            # We only need the INSTALLED_APPS from this application, but have
            # our own url patterns and don't need any other middleware.
            from django.conf import settings
            settings.ROOT_URLCONF = 'template_preprocessor.tools.open_in_editor_api.urls'
            settings.MIDDLEWARE_CLASSES = []
        patch_settings()

        # Run the server
        def _run():
            from django.conf import settings
            from django.utils import translation

            print 'Open-in-editor server started'

            try:
                run(addr, int(port), WSGIHandler())
            except WSGIServerException, e:
                # Use helpful error messages instead of ugly tracebacks.
                ERRORS = {
                    13: "You don't have permission to access that port.",
                    98: "That port is already in use.",
                    99: "That IP address can't be assigned-to.",
                }
                try:
                    error_text = ERRORS[e.args[0].args[0]]
                except (AttributeError, KeyError):
                    error_text = str(e)
                sys.stderr.write(self.style.ERROR("Error: %s" % error_text) + '\n')
                # Need to use an OS exit because sys.exit doesn't work in a thread
                os._exit(1)
            except KeyboardInterrupt:
                if shutdown_message:
                    print shutdown_message
                sys.exit(0)
        _run()
