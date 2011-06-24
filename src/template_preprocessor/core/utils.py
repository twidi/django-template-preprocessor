
import os
import codecs
import urllib2
from hashlib import md5

from django.conf import settings
from django.utils import translation
from template_preprocessor.core.lexer import CompileException

MEDIA_ROOT = settings.MEDIA_ROOT
MEDIA_CACHE_DIR = settings.MEDIA_CACHE_DIR
MEDIA_CACHE_URL = settings.MEDIA_CACHE_URL
MEDIA_URL = settings.MEDIA_URL
STATIC_URL = getattr(settings, 'STATIC_URL', '')


# =======[ Utilities for media/static files ]======

def is_remote_url(url):
    return any(url.startswith(prefix) for prefix in ('http://', 'https://'))


def get_media_source_from_url(url):
    """
    For a given media/static URL, return the matching full path in the media/static directory
    """
    from django.contrib.staticfiles.finders import find

    # Media
    if MEDIA_URL and url.startswith(MEDIA_URL):
        return os.path.join(MEDIA_ROOT, url[len(MEDIA_URL):].lstrip('/'))

    elif MEDIA_URL and url.startswith('/media/'):
        return os.path.join(MEDIA_ROOT, url[len('/media/'):].lstrip('/'))

    # Static
    elif STATIC_URL and url.startswith(STATIC_URL):
        return find(url[len(STATIC_URL):].lstrip('/'))

    elif STATIC_URL and url.startswith('/static/'):
        return find(url[len('/static/'):].lstrip('/'))


    # External URLs
    elif is_remote_url(url):
        return url

    else:
        raise Exception('Invalid media/static url given: %s' % url)


def read_media(url):
    if is_remote_url(url):
        try:
            f = urllib2.urlopen(url)

            if f.code == 200:
                return f.read().decode('utf-8')
            else:
                raise CompileException(None, 'External media not found: %s' % url)

        except urllib2.URLError, e:
            raise CompileException(None, 'Opening %s failed: %s' % (url, e.message))
    else:
        return codecs.open(get_media_source_from_url(url), 'r', 'utf-8').read()


def simplify_media_url(url):
    """
    For a given media/static URL, replace the settings.MEDIA/STATIC_URL prefix
    by simply /media or /static.
    """
    if url.startswith(settings.STATIC_URL):
        return '/static/' + url[len(settings.STATIC_URL):]

    if url.startswith(settings.MEDIA_URL):
        return '/media/' + url[len(settings.MEDIA_URL):]

    else:
        return url


def real_url(url):
    if url.startswith('/static/'):
        return settings.STATIC_URL + url[len('/static/'):]

    elif url.startswith('/media/'):
        return settings.MEDIA_URL + url[len('/media/'):]

    else:
        return url


def check_external_file_existance(node, url):
    """
    Check whether we have a matching file in our media/static directory for this URL.
    Raise exception if we don't.
    """
    exception = CompileException(node, 'Missing external media file (%s)' % url)

    if is_remote_url(url):
        if urllib2.urlopen(url).code != 200:
            raise exception
    else:
        complete_path = get_media_source_from_url(url)

        if not complete_path or not os.path.exists(complete_path):
            if MEDIA_URL and url.startswith(MEDIA_URL):
                raise exception

            elif STATIC_URL and url.startswith(STATIC_URL):
                raise exception


def _create_directory_if_not_exists(directory):
    """
    Create a directory (for cache, ...) if this one does not yet exist.
    """
    if not os.path.exists(directory):
        #os.mkdir(directory)
        os.makedirs(directory)


def need_to_be_recompiled(source_files, output_file):
    """
    Returns True when one of the source files in newer then the output_file
    """
    return (
        # Output does not exists
        not os.path.exists(output_file) or

        # Any local input file has been changed after generation of the output file
        # (We don't check the modification date of external javascript files.)
        any(not is_remote_url(s) and os.path.getmtime(s) > os.path.getmtime(output_file) for s in map(get_media_source_from_url, source_files))
    )


def create_media_output_path(media_files, extension, lang):
    assert extension in ('js', 'css')

    name = '%s.%s' % (os.path.join(lang, md5(''.join(media_files)).hexdigest()), extension)
    return os.path.join(MEDIA_CACHE_DIR, name)


# =======[ Compiler for external media/static files ]======


def compile_external_javascript_files(media_files, context, compress_tag=None):
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
        context.compile_media_callback(compress_tag, map(simplify_media_url, media_files))
        progress = [0] # by reference

        def compile_part(media_file):
            progress[0] += 1
            media_content = read_media(media_file)

            context.compile_media_progress_callback(compress_tag, simplify_media_url(media_file),
                        progress[0], len(media_files), len(media_content))

            if not is_remote_url(media_file) or context.options.compile_remote_javascript:
                return compile_javascript_string(media_content, context, media_file)
            else:
                return media_content

        # Concatenate and compile all scripts
        source = u'\n'.join(compile_part(p) for p in media_files)

        # Store in media dir
        _create_directory_if_not_exists(os.path.split(compiled_path)[0])
        codecs.open(compiled_path, 'w', 'utf-8').write(source)

        # Store meta information
        open(compiled_path + '-c-meta', 'w').write('\n'.join(map(simplify_media_url, media_files)))

    return os.path.join(MEDIA_CACHE_URL, name)


def compile_external_css_files(media_files, context, compress_tag=None):
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
        context.compile_media_callback(compress_tag, map(simplify_media_url, media_files))
        progress = [0] # by reference

        def compile_part(media_file):
            progress[0] += 1
            media_content = read_media(media_file)

            context.compile_media_progress_callback(compress_tag, simplify_media_url(media_file),
                        progress[0], len(media_files), len(media_content))

            if not is_remote_url(media_file) or context.options.compile_remote_css:
                return compile_css_string(media_content, context, get_media_source_from_url(media_file), media_file)
            else:
                return media_content

        # concatenate and compile all css files
        source = u'\n'.join(compile_part(p) for p in media_files)

        # Store in media dir
        _create_directory_if_not_exists(os.path.split(compiled_path)[0])
        codecs.open(compiled_path, 'w', 'utf-8').write(source)

        # Store meta information
        open(compiled_path + '-c-meta', 'w').write('\n'.join(map(simplify_media_url, media_files)))

    return os.path.join(MEDIA_CACHE_URL, name)
