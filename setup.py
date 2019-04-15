from setuptools import setup, find_packages

# discord.py dependency is kind of hack-y due to limitations in setup
# If you want to be pure about it, change the version in
#   the dependency_links entry from 10 to 1.0.0a0 or whatever version
#   and the same in install_requires from >0.9 to ==version

setup(
    name='jshbot',
    author='Jsh',
    url='https://github.com/jkchen2/JshBot',
    version='0.4.0a1',
    packages=find_packages(),
    license='MIT',
    dependency_links=[
        'https://github.com/Rapptz/discord.py/archive/master.zip#egg=discord.py-10'
    ],
    install_requires=[
        'discord.py[voice]>0.9',
        'pyyaml',
        'psycopg2-binary'
    ]
)
