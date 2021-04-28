import setuptools

with open('README.rst') as f:
    readme = f.read()

with open('HISTORY.rst') as f:
    history = f.read()

setuptools.setup(name='mixcloud3',
                 version='0.5.0+dev',
                 author='Etienne Millon, Ben Tappin, Marcin Baryłka',
                 author_email='marcin.barylka@radiospacja.pl',
                 url="https://github.com/Radiospacja/mixcloud3",
                 license='BSD',
                 packages=['mixcloud3'],
                 install_requires=[
                     'python-dateutil',
                     'requests',
                     'pyyaml',
                     'python-slugify'
                 ],
                 description='Bindings for the mixcloud.com API',
                 long_description=readme + '\n\n' + history,
                 classifiers=[
                     'Development Status :: 3 - Alpha',
                     'Intended Audience :: Developers',
                     'License :: OSI Approved :: BSD License',
                     'Operating System :: OS Independent',
                     'Programming Language :: Python :: 3',
                     ],
                 )
