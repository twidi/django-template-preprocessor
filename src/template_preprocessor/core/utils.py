
import os
import codecs
from hashlib import md5

from django.conf import settings
from django.utils import translation

MEDIA_ROOT = settings.MEDIA_ROOT
MEDIA_CACHE_DIR = settings.MEDIA_CACHE_DIR
MEDIA_CACHE_URL = settings.MEDIA_CACHE_URL
MEDIA_URL = settings.MEDIA_URL
STATIC_URL = getattr(settings, 'STATIC_URL', '')


# =======[ Utilities for media/static files ]======

def get_media_source_from_url(url):
    """
    For a given media/static URL, return the matching full path in the media/static directory
    """
    if MEDIA_URL and url.startswith(MEDIA_URL):
        return os.path.join(MEDIA_ROOT, url[len(MEDIA_URL):].lstrip('/'))

    elif STATIC_URL and url.startswith(STATIC_URL):
        from django.contrib.staticfiles.finders import find
        path = url[len(STATIC_URL):].lstrip('/')
        return find(path)



def check_external_file_existance(node, url):
    """
    Check whether we have a matching file in our media/static directory for this URL.
    Raise exception if we don't.
    """
    complete_path = get_media_source_from_url(url)

    if not complete_path or not os.path.exists(complete_path):
        if MEDIA_URL and url.startswith(MEDIA_URL):
            raise CompileException(node, 'Missing external media file (%s)' % url)

        elif STATIC_URL and url.startswith(STATIC_URL):
            raise CompileException(node, 'Missing external static file (%s)' % url)


def _create_directory_if_not_exists(directory):
    if not os.path.exists(directory):
        os.mkdir(directory)



def need_to_be_recompiled(source_files, output_file):
    """
    Returns True when one of the source files in newer then the output_file
    """
    return (
        # Output does not exists
        not os.path.exists(output_file) or

        # Any input file has been changed after generation of the output file
        any(os.path.getmtime(s) > os.path.getmtime(output_file) for s in map(get_media_source_from_url, source_files))
    )

def create_media_output_path(media_files, extension, lang):
    assert extension in ('js', 'css')

    name = '%s.%s' % (os.path.join(lang, md5(''.join(media_files)).hexdigest()), extension)
    return os.path.join(MEDIA_CACHE_DIR, name)


# =======[ Compiler for external media/static files ]======


def compile_external_javascript_files(media_files, context, start_compile_callback=None):
    """
    Make sure that these external javascripts are compiled. (don't compile when not required.)
    Return output path.
    """
    from template_preprocessor.core.js_processor import compile_javascript_string

    # Create a hash for this scriptnames
    name = os.path.join(translation.get_language(), md5(''.join(media_files)).hexdigest()) + '.js'
    compiled_path = os.path.join(MEDIA_CACHE_DIR, name)

    if need_to_be_recompiled(media_files, compiled_path):
        # Trigger callback, used for printing "compiling media..." feedback
        if start_compile_callback:
            start_compile_callback()

        # concatenate and compile all scripts
        source = u'\n'.join([
                    compile_javascript_string(codecs.open(get_media_source_from_url(p), 'r', 'utf-8').read(), context, p)
                    for p in media_files ])

        # Store in media dir
        _create_directory_if_not_exists(os.path.split(compiled_path)[0])
        codecs.open(compiled_path, 'w', 'utf-8').write(source)

        # Store meta information
        open(compiled_path + '-c-meta', 'w').write('\n'.join(media_files))

    return os.path.join(MEDIA_CACHE_URL, name)


def compile_external_css_files(media_files, context, start_compile_callback=None):
    """
    Make sure that these external css are compiled. (don't compile when not required.)
    Return output path.
    """
    from template_preprocessor.core.css_processor import compile_css_string

    # Create a hash for this scriptnames
    name = os.path.join(translation.get_language(), md5(''.join(media_files)).hexdigest()) + '.css'
    compiled_path = os.path.join(MEDIA_CACHE_DIR, name)

    if need_to_be_recompiled(media_files, compiled_path):
        # Trigger callback, used for printing "compiling media..." feedback
        if start_compile_callback:
            start_compile_callback()

        # concatenate and compile all css files
        source = u'\n'.join([
                    compile_css_string(
                                codecs.open(get_media_source_from_url(p), 'r', 'utf-8').read(),
                                context,
                                os.path.join(MEDIA_ROOT, p),
                                url=os.path.join(MEDIA_URL, p))
                    for p in media_files ])

        # Store in media dir
        _create_directory_if_not_exists(os.path.split(compiled_path)[0])
        codecs.open(compiled_path, 'w', 'utf-8').write(source)

        # Store meta information
        open(compiled_path + '-c-meta', 'w').write('\n'.join(media_files))

    return os.path.join(MEDIA_CACHE_URL, name)
