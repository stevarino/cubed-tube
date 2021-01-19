import setuptools

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name="hermit_tube", # Replace with your own username
    version="0.0.1",
    author="stevarino",
    author_email="stevarino@hermit.tube",
    description="Watch HermitCraft videos!",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/stevarino/hermit-tube",
    packages=setuptools.find_packages(),
    classifiers=[
    ],
    python_requires='>=3.6',
)
