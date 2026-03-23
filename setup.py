import setuptools

setuptools.setup(
    name="gopro",
    version="0.1.0",
    packages=setuptools.find_packages(),
    install_requires=[
        "aiohttp>=3.11.14",
        "python-dotenv>=1.0.1",
        "pydantic>=2.10.6",
        "requests>=2.32.3",
    ],
)