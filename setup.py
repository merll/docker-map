from setuptools import setup, find_packages
from dockermap import __version__

setup(
    name='docker-map',
    version=__version__,
    packages=find_packages(),
    install_requires=['six', 'docker-py>=0.4.0'],
    license='MIT',
    author='Matthias Erll',
    author_email='matthias@erll.de',
    description='Integration for Docker into Fabric.',
    platforms=['OS Independent'],
    include_package_data=True,
)
