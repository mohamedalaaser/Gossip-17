"""Build system setup file."""

from setuptools import setup, find_packages

with open("README.md", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="gossip-17",
    version="0.0.1",
    description="Gossip Module for Anonymous and Unobservable VoIP Application",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Mohamed Alaaser & Khaled Hegazy",
    author_email="mohamedd.alaaser@tum.de & khaled.hegazy@tum.de",
    packages=find_packages(),
    license="MIT",
    license_files="LICENSE",
    python_requires=">=3.6",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    platforms=["any"],
    entry_points={
        "console_scripts": [
            "gossip = gossip.main:main",
        ],
    },
)
