# Django settings for test_project project.

import os

DEBUG = True
TEMPLATE_DEBUG = DEBUG

ADMINS = ()
MANAGERS = ADMINS

TIME_ZONE = 'America/Chicago'

PROJECT_DIR = os.path.dirname(__file__) + '/'

LANGUAGE_CODE = 'en-us'
USE_I18N = True
USE_L10N = True

LANGUAGES = (
    ('en', 'EN'),
    ('fr', 'FR'),
    ('nl', 'NL'),
)

MEDIA_ROOT = PROJECT_DIR + 'media/'
MEDIA_URL = '/media/'
STATIC_ROOT = PROJECT_DIR + 'static/'
STATIC_URL = '/static/'


# Template preprocessor settings
TEMPLATE_CACHE_DIR = PROJECT_DIR + 'templates/cache/'
MEDIA_CACHE_DIR = MEDIA_ROOT + 'cache/'
MEDIA_CACHE_URL = MEDIA_URL + 'cache/'

STATICFILES_FINDERS = (
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
#    'django.contrib.staticfiles.finders.DefaultStorageFinder',
)


SECRET_KEY = '7wq0^b4+mx39f%ly5ty#4nk9pwdkh%63u1!_h-x@%!hos3f9%b'


TEMPLATE_LOADERS = (
    'django.template.loaders.filesystem.Loader',
    'django.template.loaders.app_directories.Loader',
#     'django.template.loaders.eggs.Loader',
)

MIDDLEWARE_CLASSES = (
    'django.middleware.common.CommonMiddleware',
)

ROOT_URLCONF = 'test_project.urls'

TEMPLATE_DIRS = (
    os.path.join(PROJECT_DIR, 'templates')
)

INSTALLED_APPS = (
    'django.contrib.staticfiles',
    'template_preprocessor',
)
