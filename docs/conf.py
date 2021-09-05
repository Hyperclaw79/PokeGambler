# pylint: skip-file

# -- Path setup --------------------------------------------------------------

import os
import sys
sys.path.insert(0, os.path.abspath('..'))


# -- Project information -----------------------------------------------------

project = 'PokeGambler'
copyright = '2021, Harshith Thota (Hyperclaw79)'
author = 'Harshith Thota (Hyperclaw79)'

rst_epilog = f"""
.. |project| replace:: {project}
.. |author| replace:: {author}
"""

# -- General configuration ---------------------------------------------------

suppress_warnings = ['misc.highlighting_failure']
extensions = [
    'hoverxref.extension',
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.autosectionlabel",
    'sphinx.ext.coverage',
    'sphinx.ext.intersphinx',
    'sphinx.ext.viewcode',
    'sphinxext.opengraph',
    "sphinx_rtd_dark_mode",
    'sphinx_search.extension',
    'sphinx_tabs.tabs'
]
add_module_names = False

autodoc_class_signature = 'separated'
autodoc_default_options = {
    'exclude-members': '__init__'
}
autodoc_docstring_signature = False
autodoc_member_order = 'bysource'
autodoc_preserve_defaults = True
autodoc_typehints = "description"

autosummary_generate = True

coverage_ignore_classes = [
    'NameSetter',
    'PremiumShop'
]
coverage_ignore_pyobjects = [
    r'scripts\.helpers\.validators\..+\.check',
    r'scripts\.base\.enums\..+'
]
coverage_show_missing_items = True
coverage_write_headline = True

hoverxref_auto_ref = True
hoverxref_domains = ['py']
hoverxref_intersphinx = [
    'aiohttp',
    'discord',
    'Pillow',
    'topgg'
]
hoverxref_role_types = {
    'class': 'tooltip',
    'ref': 'tooltip',
    'func': 'tooltip',
    'meth': 'tooltip'
}

intersphinx_mapping = {
    'aiohttp': ('https://docs.aiohttp.org/en/stable/', None),
    'discord': ('https://discordpy.readthedocs.io/en/master/', None),
    'Pillow': ('https://pillow.readthedocs.io/en/latest/', None),
    'topgg': ('https://topggpy.readthedocs.io/en/latest/', None)
}

templates_path = ['_templates']

exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

nitpicky = True
nitpick_ignore = [
    ('py:class', 'datetime.datetime'),
]
nitpick_ignore_regex = [
    ('py:class', r'[^:]+:\s[^=\s]+(\s=\s.+)?'),
    ('py:class', r'[^:]?:\s[^=\s]+\s=\s.+'),
    ('py:class', r'[a-zA-Z_-]+'),
    ('py:class', r'[^:]?:\s[a-zA-Z_-]+'),
]

ogp_image = 'https://pokegambler.readthedocs.io/en/latest/_images/logochip.png'

python_use_unqualified_type_names = True

# -- Options for HTML output -------------------------------------------------

html_theme = 'sphinx_rtd_theme'

html_static_path = ['_static']

html_css_files = [
    'css/spoiler.css',
]

html_js_files = [
    'js/spoiler.js',
]

html_favicon = '_static/favicon.ico'

default_dark_mode = True


def setup(app):
    import re

    from sphinx.ext.autodoc import cut_lines

    command_prefix = os.environ.get("COMMAND_PREFIX", "->")
    arg_info_patt = re.compile(r"#.+#")

    def format_docs(app, what, name, obj, options, lines):
        cut_lines(17, what=['module'])(
            app, what, name, obj, options, lines
        )
        # For Commands
        for idx, line in enumerate(lines):
            lines[idx] = arg_info_patt.sub(
                '',
                line.replace(
                    "{command_prefix}", command_prefix
                ).replace(
                    "{pokechip_emoji}", "Pokechips"
                )
            )
        if (
            hasattr(obj, "alias")
            and isinstance(obj.alias, list)
            and obj.alias
        ):
            alias_str = ', '.join(
                f":class:`{alias}<{obj.__module__}.{obj.__qualname__}>`"
                for alias in obj.alias
            )
            lines.extend([
                ".. rubric:: Aliases",
                "",
                alias_str,
                ""
            ])
        if (
          hasattr(obj, "models")
          and isinstance(obj.models, list)
          and obj.models
        ):
            model_str = ', '.join(
                f":class:`~{model.__module__}.{model.__qualname__}`"
                for model in obj.models
            )
            lines.extend([
                ".. rubric:: Models",
                "",
                model_str
            ])

    def clean_sigs(app, what, name, obj, options, signature, return_annotation):
        return ('', return_annotation)

    app.connect('autodoc-process-docstring', format_docs)
    app.connect('autodoc-process-signature', clean_sigs)
