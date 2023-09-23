from setuptools import find_packages, setup

setup(
    name="crpy",
    version="0.0.1",
    packages=find_packages(),
    description="Simple and straight forward async library for interacting with container registry API.",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="Brunno Vanelli",
    author_email="brunnovanelli@gmail.com",
    url="https://github.com/bvanelli/crpy",
    zip_safe=False,
    project_urls={
        "Issues": "https://github.com/bvanelli/crpy/issues",
    },
    entry_points="""
      [console_scripts]
      crpy=crpy.cmd:main
      """,
)
