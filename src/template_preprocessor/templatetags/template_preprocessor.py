"""
Author: Jonathan Slenders, City Live

Following tag is a dummy tag. If the preprocessor is not used,
the tag should not output anything. If the preprocessor is enabled,
the tag is used to determine which optimizations are enabled.
"""
from django import template
from django.utils.safestring import mark_safe
from django.template import Library, Node, resolve_variable

register = template.Library()

class DummyTag(Node):
    """
    Dummy tag to make sure these preprocessor tags
    don't output anything if the preprocessor has been disabled.
    """
    def __init__(self):
        pass

    def render(self, context):
        return u''


@register.tag(name="!")
def preprocessor_option(parser, token):
    """
    # usage: {% ! no-whitespace-compression no-js-minify %}
    """
    return DummyTag()


@register.tag(name='compress')
def pack(parser, token):
    """
    # usage: {% compress %} ... {% endcompress %}
    Contains CSS or javascript files which are to be packed together.
    """
    return DummyTag()


@register.tag(name='endcompress')
def pack(parser, token):
    return DummyTag()


@register.tag(name='!raw')
def pack(parser, token):
    """
    # usage: {% !raw %} ... {% !endraw %}
    Contains a block which should not be html-validated.
    """
    return DummyTag()


@register.tag(name='!endraw')
def pack(parser, token):
    return DummyTag()
