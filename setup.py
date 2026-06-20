from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = []
    for line in fh:
        requirement = line.split("#", 1)[0].strip()
        if requirement:
            requirements.append(requirement)

setup(
    name="neohub-control",
    version="0.2.4",
    author="DAK",
    description="MQTT bridge and Home Assistant add-on for Heatmiser NeoHub systems",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/GitDakky/NeoHub-Control",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "neohub-control=cli:main",
        ],
    },
)
