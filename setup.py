"""
Setup configuration for The Deterministic Jungle Canopy.
"""
from setuptools import setup, find_packages

setup(
    name="canopy",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "numpy>=1.24.0",
        "scipy>=1.10.0",
        "Pillow>=10.0.0",
    ],
    extras_require={
        "server": [
            "fastapi>=0.100.0",
            "uvicorn[standard]>=0.23.0",
            "pydantic>=2.0.0",
        ],
        "dev": [
            "pytest>=7.4.0",
            "pytest-asyncio>=0.21.0",
            "httpx>=0.24.0",
        ]
    },
    python_requires=">=3.9",
    author="The Prophet",
    description="Deterministic procedural image/video processing pipeline",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/awkawk/canopy",
)
