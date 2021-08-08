import glob
import os.path
import setuptools

DIR = os.path.dirname(__file__)
with open(os.path.join(DIR, "README.md"), "r", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name="cubedtube", # Replace with your own username
    version="0.1.10.dev1",
    author="stevarino",
    author_email="stevarino@hermit.tube",
    description="A video viewing webapp that organizes videos into channels and series",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/stevarino/cubed-tube",
    project_urls={
        "Bug Tracker": "https://github.com/stevarino/cubed-tube/issues",
    },
    packages=setuptools.find_packages(),
    package_data={'cubed_tube.frontend.templates': ['*', '**/*']},
    install_requires=[
        'Authlib<=0.15.4',  # Authlib 1.0a has signature changes
        'awscli>=1.19.97',
        'boto3>=1.17.97',
        'Flask>=1.1.2',
        'Jinja2>=3.0',
        'peewee>=3.13.3',
        'prometheus-client>=0.11.0',
        'pymemcache>=3.5.0',
        'PyYAML>=5.3.1',
        'requests>=2.0'
    ],
    classifiers=[
    ],
    entry_points = {
        'console_scripts': ['cubedtube=cubed_tube.main:main'],
    },
    python_requires='>=3.6',
)
