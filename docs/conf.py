# pylint: skip-file

# -- Path setup --------------------------------------------------------------

import inspect
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
    'css/spoiler.css'
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
    colon_enclosed_patt = re.compile(r":(?P<attr>[^:]+)\s(?P<name>.+):\s(?P<value>.+)")

    def format_docs(app, what, name, obj, options, lines):
        cut_lines(17, what=['module'])(
            app, what, name, obj, options, lines
        )
        # For Commands
        param_dict = {}
        for idx, line in enumerate(lines.copy()):
            lines[idx] = arg_info_patt.sub(
                '',
                line.replace(
                    "{command_prefix}", command_prefix.replace("'", "")
                ).replace(
                    "{pokechip_emoji}", "Pokechips"
                )
            )
            if name.split('.')[-1].startswith('cmd_'):
                populate_param_table(lines, param_dict, idx, line)
        add_alias(obj, lines)
        add_models(obj, lines)
        for _ in range(lines.count('<DEL>')):
            lines.remove('<DEL>')
        add_param_table(lines, param_dict)

    def add_models(obj, lines):
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

    def add_alias(obj, lines):
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

    def add_param_table(lines, param_dict):
        def get_elem(idx, attr):
            return f"    {'*' if idx == 0 else ' '} - {attr.title()}"

        if param_dict:
            lines.extend([
                "",
                ".. rubric:: Parameter Config",
                ""
            ])
            justify = (
                ' justify-content: space-evenly;' if len(param_dict) > 1
                else ''
            )
            lines.extend([
                ".. raw:: html",
                "",
                f"    <div style='display: flex;{justify}'>",
            ])
        for param_name, attrs in param_dict.items():
            lines.extend([
                f".. list-table:: **{param_name.title()}**",
                "",
                *[get_elem(idx, attr) for idx, attr in enumerate(attrs)],
                *[get_elem(idx2, val) for idx2, val in enumerate(attrs.values())],
                "",
            ])
        if param_dict:
            lines.extend([
                ".. raw:: html",
                "",
                "    </div>",
                ""
            ])

    def populate_param_table(lines, param_dict, idx, line):
        is_coloned = colon_enclosed_patt.search(line)
        valids = ('default', 'min_value', 'max_value', 'choices')
        if is_coloned and is_coloned.group('attr') in valids:
            group = is_coloned.groupdict()
            if group['name'] not in param_dict:
                param_dict[group['name']] = {}
            param_dict[group['name']][group['attr']] = group['value']
            lines[idx] = '<DEL>'

    def clean_sigs(app, what, name, obj, options, signature, return_annotation):
        return ('', return_annotation)

    app.connect('autodoc-process-docstring', format_docs)
    app.connect('autodoc-process-signature', clean_sigs)
