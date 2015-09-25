from distutils.spawn import find_executable
import os
from setuptools import setup, find_packages

from dockermap import __version__


def include_readme():
    try:
        import pandoc
    except ImportError:
        return ''
    pandoc.core.PANDOC_PATH = find_executable('pandoc')
    readme_file = os.path.join(os.path.dirname(__file__), 'README.md')
    doc = pandoc.Document()
    with open(readme_file, 'r') as rf:
        doc.markdown = rf.read()
        return doc.rst


setup(
    name='docker-map',
    version=__version__,
    packages=find_packages(),
    install_requires=['six', 'docker-py>=1.1.0'],
    extras_require={
        'yaml': ['PyYAML'],
    },
    license='MIT',
    author='Matthias Erll',
    author_email='matthias@erll.de',
    url='https://github.com/merll/docker-map',
    description='Managing Docker images, containers, and their dependencies in Python.',
    long_description=include_readme(),
    platforms=['OS Independent'],
    keywords=['docker', 'deployment'],
    classifiers=[
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Topic :: Software Development :: Build Tools',
        'Topic :: System :: Software Distribution',
        'Development Status :: 4 - Beta',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
    ],
    include_package_data=True,
)
