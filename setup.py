from pathlib import Path

import setuptools

ROOT = Path(__file__).resolve().parent
README = (ROOT / "README.md").read_text(encoding="utf-8")

setuptools.setup(
    name="gopro-api",
    version="0.0.3",
    author="himewel",
    author_email="welberthime@gmail.com",
    description=(
        "Unofficial async Python client for the GoPro cloud media API "
        "(api.gopro.com), using aiohttp and Pydantic."
    ),
    long_description=README,
    long_description_content_type="text/markdown",
    url="https://github.com/himewel/gopro-api",
    project_urls={
        "Bug Tracker": "https://github.com/himewel/gopro-api/issues",
        "Source": "https://github.com/himewel/gopro-api",
    },
    license="MIT",
    license_files=["LICENSE"],
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Environment :: Web Environment",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3 :: Only",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Multimedia :: Graphics :: Capture :: Digital Camera",
    ],
    keywords="gopro quik cloud api async aiohttp media gopro-api",
    packages=setuptools.find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "aiohttp~=3.11.14",
        "python-dotenv~=1.0.1",
        "pydantic~=2.10.6",
        "requests~=2.32.3",
    ],
    extras_require={
        "dev": [
            "build~=1.0.0",
        ],
    },
)
