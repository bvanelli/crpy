from setuptools import find_packages, setup

setup(
    name="crpy",
    packages=find_packages(),
    description="Simple and straight forward wrapper for container registry API.",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="Brunno Vanelli",
    author_email="brunnovanelli@gmail.com",
    url="https://github.com/bvanelli/docker-pull-push",
    zip_safe=False,
    project_urls={
        "Issues": "https://github.com/bvanelli/docker-pull-push/issues",
    },
    entry_points="""
      [console_scripts]
      crpy=crpy.cmd:main
      """,
)
