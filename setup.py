from setuptools import setup, find_packages

setup(
    name='gaming-market-engine',
    version='0.1.0',
    packages=find_packages(include=['app.engine', 'app.engine.*']),
    install_requires=[
        'decimal',
        'mpmath',
        'numpy',
        'typing_extensions',
    ],
    description='Deterministic Python engine for the Gaming Market Demo AMM, including state management, order processing, and resolutions.',
    author='xAI',
    author_email='info@x.ai',
    url='https://x.ai',
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.12',
)