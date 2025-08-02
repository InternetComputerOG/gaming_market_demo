# setup.py_context.md

## Overview
Packaging script for the Gaming Market Demo's engine package, enabling installation for testing and reuse per implementation plan's repository structure. Defines a simple setuptools configuration for the 'gaming-market-engine' package.

## Key Exports/Interfaces
- No exported functions or classes; executes `setup()` from setuptools to define package metadata and dependencies.

## Dependencies/Imports
- Imports: setuptools (setup, find_packages).
- Interactions: References app/engine directory for packaging; install_requires lists engine-specific deps (decimal, mpmath, numpy, typing_extensions) from requirements.txt; no runtime calls to other files.

## Usage Notes
- Run `python setup.py install` to package/install engine locally for unit tests; JSON-compatible with demo (no direct serialization); ties to TDD by supporting numpy for quadratics in engine/amm_math.py. Use for demo-scale testing without full app.

## Edge Cases/Invariants
- Invariants: Package name/version fixed; install_requires ensures numerical stability (numpy for solves). Edges: Missing deps raise errors; deterministic packaging (no dynamic content). Assumes Python >=3.12 per classifiers.