"""
PokeGambler - A Pokemon themed gambling bot for Discord.
Copyright (C) 2021 Harshith Thota

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
----------------------------------------------------------------------------

RestructuredText and Parameter parsers
"""

import re
from functools import cached_property
from typing import Any, Dict, List, Optional

from ..base.enums import OptionTypes


class Options(dict):
    """
    A dictionary with attribute access.
    """
    def __getattr__(self, name: str) -> Optional[str]:
        return self.get(name)

    def __setattr__(self, name: str, value: str) -> None:
        self[name] = value


class Directive:
    """
    A simple Class which corresponds to reStructureText directive.

    :param argument: The argument of the directive.
    :type argument: Optional[str]
    """
    def __init__(self, argument: Optional[str] = None):
        self.role_pattern = re.compile(
            r':.+:`(.+)`'
        )
        self.argument = argument
        self.options = Options()
        self.lines = []
        self.children = []

    def __getattr__(self, name: str):
        if name not in dir(self):
            return self.options.get(name)
        return self.__dict__[name]

    @property
    def line_string(self) -> str:
        """
        Converts the lines of the directive into a single string.

        :return: The string of the lines.
        :rtype: str
        """
        if self.__class__.__name__ == 'Rubric':
            line_str = '\n'.join(
                child.to_string() if isinstance(child, Directive)
                else child
                for child in self.children
            )
        else:
            line_str = '\n'.join(self.lines)
        if self.role_pattern.search(line_str):
            ctx = self.role_pattern.search(line_str).group(1)
            line_str = self.role_pattern.sub(
                r'\|\|\1\|\|', line_str
            )
            line_str = self.role_pattern.sub(
                ctx.split('.')[-1], line_str
            )
        return line_str

    def to_string(self) -> str:
        """
        Converts the directive into a string represenation
        meant for usage in Discord Embeds.

        :param ext: The extension for markdown.
        :type ext: Optional[str]
        :return: The string representation of the directive.
        :rtype: str
        """
        cls_name = self.__class__.__name__
        emoji_dict = {
            'Note': ':information_source:',
            'Warning': ':warning:',
            'Tip': ':bulb:'
        }
        if cls_name == 'Rubric':
            return self.line_string
        if cls_name == 'Code':
            if not self.argument:
                ext = ''
            elif self.argument == 'coffee':
                ext = 'scss'
            else:
                ext = self.argument
            return f"```{ext}\n{self.line_string}\n```"
        if cls_name == 'Admonition':
            return f":information_source: **{self.argument}**" + \
                f"```\n{self.line_string}\n```"
        if cls_name in emoji_dict:
            return f"{emoji_dict[cls_name]} **{cls_name}**\n" + \
                f"```\n{self.line_string}\n```"
        return ""


class Param:
    """
    A simple Class which corresponds to function parameters.

    :param name: The name of the parameter.
    :type name: str
    :param description: The description of the parameter.
    :type description: str
    """

    # pylint: disable=too-few-public-methods,too-many-instance-attributes

    def __init__(
        self, name: str,
        description: Optional[str] = None
    ):
        self.name = name
        self.description = description
        self.type = None
        self.default = None
        self.choices = None
        self.min_value = None
        self.max_value = None
        self.autocomplete = False
        self._parse_pattern = re.compile(
            r'[ld]i[sc]t\[(.+)\]',
            re.IGNORECASE
        )
        self._vals_pattern = re.compile(
            r'(?P<name>[^#]+)(?:#(?P<description>.+)#)?:\s'
            r'(?P<type>[a-zA-Z_\[\]]+)'
            r'(?:\s=\s(?P<default>[^\]]+))?'
        )
        self._discord_pattern = re.compile(
            r':class:`discord\.(.+)`'
        )
        self._optional_pattern = re.compile(
            r'Optional\[(.+)\]'
        )
        self._list_pattern = re.compile(
            r'\[(.+)\]'
        )

    def __repr__(self) -> str:
        cleaned_type = self._discord_pattern.sub(
            r'\1',
            self._optional_pattern.sub(r'\1', self.type)
        )
        required = 'Optional' not in str(self.type)
        return f'Param(name={self.name}, type={cleaned_type}, ' \
            f'description={self.description}, ' \
            f'default={self.default}, ' \
            f'required={required})'

    def __setattribute__(self, name: str, value: Any) -> None:
        setattr(self, name, value)
        if name == 'choices':
            self.__resolve_choices()

    def parse(self) -> Dict[str, Any]:
        """Resolves the parameter type into attributes
        using regular expressions.

        :return: The resolved parameters.
        :rtype: Dict[str, Any]
        """
        if self.name == 'message':
            return []
        parsed = {
            attr: getattr(self, attr)
            for attr in (
                'name', 'description', 'type',
                'default', 'autocomplete'
            )
        }
        parsed["autocomplete"] = parsed["autocomplete"] == 'True'
        self.__resolve_special_types(parsed)
        parsed['required'] = 'Optional' not in parsed['type']
        parsed['type'] = OptionTypes[
            self._optional_pattern.sub(r'\1', parsed['type'])
        ]
        parsed['description'] = parsed.get(
            'description'
        ) or 'Please enter a value.'
        if parsed.get('default') is not None:
            if parsed['default'] == 'None':
                parsed['default'] = None
            elif parsed['type'] == OptionTypes.INTEGER:
                parsed['default'] = int(parsed['default'])
            elif parsed['type'] == OptionTypes.NUMBER:
                parsed['default'] = float(parsed['default'])
            elif parsed['type'] == OptionTypes.BOOLEAN:
                parsed['default'] = parsed['default'] == 'True'
            parsed['description'] += f" Default is {parsed['default']}."
        operation = str
        if parsed['type'] == OptionTypes.INTEGER:
            operation = int
        elif parsed['type'] == OptionTypes.NUMBER:
            operation = float
        if parsed['type'] in (OptionTypes.INTEGER, OptionTypes.FLOAT):
            for attr in ('min_value', 'max_value'):
                if getattr(self, attr) is not None:
                    parsed[attr] = operation(getattr(self, attr))
        parsed['type'] = parsed['type'].value
        if self.choices is not None:
            self.__resolve_choices(operation)
            parsed['choices'] = self.choices
        return parsed

    def __resolve_choices(self, operation=None):
        if isinstance(self.choices, list):
            return
        choice_str = self._list_pattern.sub(r'\1', self.choices)
        self.choices = [
            {
                "name": choice.strip(),
                "value": (
                    operation(choice.strip()) if operation
                    else choice.strip()
                )
            }
            for choice in choice_str.split(',')
            if choice.strip()
        ]

    def __resolve_special_types(self, parsed: Dict[str, Any]) -> None:
        """
        Handler for discord types like User, Member, Channel, etc.
        """
        parsed['type'] = self._discord_pattern.sub(r'\1', parsed['type'])
        if 'Member' in parsed['type']:
            parsed['type'] = parsed['type'].replace('Member', 'User')


class CustomRstParser:
    """
    | A barebones reStructuredText parser using Regex.
    | Can also be used in Context Manager mode.

    .. note::
        Might be switched to an AST based one in the future.

    .. rubric:: Example
    .. code:: python

        >>> from scripts.utils.parsers import CustomRstParser
        >>> with open('README.rst') as f:
        ...     data = f.read()
        >>> # As an object.
        >>> parser = CustomRstParser()
        >>> parser.parse(data)
        >>> print(
        ...     parser.sections[0].to_string()
        ... )
        >>> # As a context manager.
        >>> with CustomRstParser() as parser:
        ...     parser.parse(data)
        ...     print(
        ...         parser.sections[0].to_string()
        ...     )
        >>> assert parser.sections == []
    """
    def __init__(self):
        param_patts = [
            re.compile(
                fr':(?P<attr>{attr})\s(?P<name>[^:]+):(?:\s(?P<value>.+))?$'
            )
            for attr in (
                'param', 'type', 'default',
                'choices', 'min_value', 'max_value',
                'autocomplete'
            )
        ]
        self._patterns = [
            re.compile(
                r'^\.\. (?P<directive>\w+)\:\:(?:\s(?P<argument>.+))?$'
            ),
            re.compile(
                r':(?P<option>\w+):(?:\s(?P<value>.+))?$'
            )
        ] + param_patts + [
            re.compile(r'\s{4}.+')
        ]
        self._tab_space = 8
        #: Meta :class:`Directive`
        #:
        #: .. tip::
        #:
        #:     There's usually only one Meta directive per docstring.
        self.meta = None
        #: All the parsed :class:`Directive`.
        self.directives = []
        #: All the parsed :class:`Param`.
        self.params = {}
        #: Rubric sections containing child :class:`Directive`.
        self.sections = []
        #: Additional lines before Params.
        self.info = ""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.info = ""
        self.directives = []
        self.params = {}
        self.sections = []

    @cached_property
    def parsed_params(self) -> List[Dict[str, Any]]:
        """Returns a list of parsed parameters.

        :return: The parsed params.
        :rtype: List[Dict[str, Any]]
        """
        return [
            param.parse()
            for param in self.params.values()
            if param.name != 'message'
        ]

    @property
    def param_names(self) -> List[str]:
        """Returns a list of parsed parameter names.

        :return: The parsed params.
        :rtype: List[str]
        """
        return [
            param['name']
            for param in self.parsed_params
        ]

    def parse(self, text: str):
        """
        Parses the given text and updates the internal sections,
        directives and parameters.

        :param text: The reST text (docstrings) to parse.
        :type text: str
        """
        for line in text.splitlines():
            (
                dir_matches, options,
                param, *param_attrs
            ) = [
                pattern.search(line.strip())
                for pattern in self._patterns[:-1]
            ]
            if dir_matches:
                self.__handle_directives(dir_matches)
            elif param:
                param = param.groupdict()
                self.params[param['name']] = Param(
                    param['name'],
                    self.__clean_line(
                        param.get('value')
                    )
                )
            elif any(param_attrs):
                for attr in param_attrs:
                    if attr:
                        attr = attr.groupdict()
                        setattr(
                            self.params[attr['name']],
                            attr['attr'], attr['value']
                        )
            elif options and self.directives:
                options = options.groupdict()
                self.directives[-1].options.update({
                    options['option']: self.__clean_line(
                        options.get('value')
                    )
                })
            elif line and (
                self.directives or self.sections or self.meta
            ):
                self.__handle_line(line)
            elif line:
                self.info += self.__clean_line(line)

    def __handle_line(self, line):
        pre_dedent_line = line.replace(' ', '', self._tab_space)
        if self._patterns[-1].search(pre_dedent_line):
            if self.directives:
                self.directives[-1].lines.append(
                    self.__clean_line(line)
                )
            else:
                self.meta.options[
                    self.meta.options.keys()[-1]
                ] += f" {self.__clean_line(line)}"
        else:
            self.sections[-1].children.append(
                self.__clean_line(line)
            )

    @staticmethod
    def __clean_line(line: str) -> str:
        return (
            None if not line
            else line.lstrip(' ' * 4)
        )

    def __handle_directives(self, dir_matches):
        dir_matches = dir_matches.groupdict()
        self.directives.append(
            type(
                dir_matches['directive'].title(),
                (Directive, ),
                {}
            )(
                self.__clean_line(
                    dir_matches.get('argument')
                )
            )
        )
        if dir_matches['directive'].title() == 'Rubric':
            self.sections.append(
                self.directives[-1]
            )
        elif dir_matches['directive'].title() == 'Meta':
            self.meta = self.directives[-1]
        elif self.sections:
            self.sections[-1].children.append(
                self.directives[-1]
            )
