# pytest-pgtap documentation build configuration

from pathlib import Path

import tomllib  # ty: ignore[unresolved-import]

PYPROJECT_FILE = Path(__file__).parents[2] / 'pyproject.toml'
with PYPROJECT_FILE.open('rb') as f:
    pyproject = tomllib.load(f)

version = pyproject['project']['version']

project = 'pytest-pgtap'
author = 'Brendan McCollam & Luke Mergner'
copyright = '2026, Brendan McCollam & Luke Mergner'

extensions = [
    'myst_parser',
]

# Source files
source_suffix = {
    '.rst': 'restructuredtext',
    '.md': 'markdown',
}
master_doc = 'index'
exclude_patterns = []

# HTML output
html_theme = 'alabaster'
html_static_path = ['_static']
pygments_style = 'sphinx'
