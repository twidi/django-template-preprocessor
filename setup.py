from setuptools import setup, find_packages

setup(
    name = "django-template-preprocessor",
    url = 'https://github.com/citylive/django-template-preprocessor',
    license = 'BSD',
    description = "Template preprocessor/compiler for Django",
    long_description = open('README.rst','r').read(),
    author = 'Jonathan Slenders, City Live nv',
    packages = find_packages('src'),
    package_data = {'template_preprocessor': ['templates/*.html', 'templates/*/*.html', 'templates/*/*/*.html'],},
    include_package_data=True,
    package_dir = {'': 'src'},
    zip_safe=False, # Don't create egg files, Django cannot find templates in egg files.
    classifiers = [
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Programming Language :: Python',
        'Operating System :: OS Independent',
        'Environment :: Web Environment',
        'Framework :: Django',
        'Topic :: Software Development :: Internationalization',
    ],
)

