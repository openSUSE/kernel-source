from setuptools import setup

setup(
    name='www-authenticate',
    version='0.9.2',
    description='Parser for WWW-Authenticate headers.',
    long_description=open('README.rst').read(),
    author='Alexander Dutton',
    author_email='www-authenticate-lib@alexdutton.co.uk',
    url='https://github.com/alexsdutton/www-authenticate',
    license='BSD',
    py_modules=['www_authenticate'],
    tests_require=['nose'],
    test_suite='nose.collector',
)
