"""
Author: Jonathan Slenders, City Live

Management command for validating HTML in model instances.
It will use the HTML parser/validator from the template proprocessor.
"""
import os
import termcolor

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import LabelCommand

from template_preprocessor.core import compile
from template_preprocessor.core.lexer import CompileException
from template_preprocessor.core.html_processor import compile_html_string

from template_preprocessor.utils import language


class Command(LabelCommand):
    """
    ./manage.py validate_html_in_model app_label.model.field

    Examples:
    ./manage.py validate_html_in_model blog.entry.body
    ./manage.py validate_html_in_model faq.faqtranslation.question faq.faqtranslation.answer
    ./manage.py validate_html_in_model flatpages.flatpage.content
    """
    help = 'Validate HTML in models.'
    args = 'app_label model field'

    def print_error(self, text):
        self._errors.append(text)
        print termcolor.colored(text, 'white', 'on_red')

    def handle_label(self, label, **options):
        self._errors = []

        args = label.split('.')
        if not len(args) == 3:
            print 'Not enough items (app_label.model.field)'
            print self.__doc__
            return

        app_label, model, field = args
        class_ = ContentType.objects.get(app_label=app_label, model=model).model_class()

        total = 0
        succes = 0

        for lang in ('en', 'fr', 'nl'):
            with language(lang):
                for i in class_.objects.all():
                    total += 1
                    print termcolor.colored('(%s) %s %i' % (lang, unicode(i), i.id), 'green')
                    try:
                        # TODO: maybe pass preprocessor options somehow.
                        #       at the moment, the default settings are working.
                        compile_html_string(getattr(i, field), path='%s (%i)' % (unicode(i), i.id) )
                        succes += 1

                    except CompileException, e:
                        self.print_error(unicode(e))

        # Show all errors once again.
        print u'\n*** %s Compile Errors ***' % len(self._errors)
        for e in self._errors:
            print termcolor.colored(e)
            print

        print ' %i / %i succeeded' % (succes, total)

        # Ring bell :)
        print '\x07'
