import setuptools

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name="cubedtube", # Replace with your own username
    version="0.1.0",
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
    classifiers=[
    ],
    python_requires='>=3.6',
)
