from setuptools import setup, find_packages

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name='nanowallet',
    version='0.0.11',
    packages=find_packages(),
    install_requires=[
        'nano_lib_py',
        'nanorpc',
    ],
    python_requires='>=3.7',
    author='gr0vity',
    url="https://github.com/gr0vity-dev/nanowallet_py",
    description='async nano library for easy account management',
    long_description=long_description,
    long_description_content_type="text/markdown"
)
