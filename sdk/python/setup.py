"""Setup for the Perennia AI Python SDK."""
from setuptools import setup, find_packages

setup(
    name="perennia-ai",
    version="0.1.0",
    description="Official Python SDK for the Perennia AI mortgage platform.",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="Perennia AI",
    author_email="engineering@perenniaai.com",
    url="https://perenniaai.com",
    packages=find_packages(exclude=("tests", "tests.*")),
    python_requires=">=3.8",
    install_requires=[],  # stdlib only — keep dependency surface minimal.
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: Other/Proprietary License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
)
