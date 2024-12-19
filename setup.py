from setuptools import setup, find_packages

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name='nanowallet',
    version='0.0.15',
    packages=find_packages(),
    install_requires=[
        'nano_lib_py==0.5.1',
        'nanorpc==0.1.7',
    ],
    python_requires='>=3.7',
    author='gr0vity',
    url="https://github.com/gr0vity-dev/nanowallet_py",
    description='async nano library for easy account management',
    long_description=long_description,
    long_description_content_type="text/markdown"
)
