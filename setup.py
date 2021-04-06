from setuptools import setup, find_packages

setup(
    name='jshbot',
    author='Jsh',
    url='https://github.com/jkchen2/JshBot',
    version='0.4.0a1',
    packages=find_packages(),
    license='MIT',
    install_requires=[
        'discord.py[voice]',
        'pyyaml',
        'psycopg2-binary'
    ]
)
