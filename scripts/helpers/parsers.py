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

    # pylint: disable=too-few-public-methods

    def __init__(
        self, name: str,
        description: Optional[str] = None
    ):
        self.name = name
        self.description = description
        self.type = None
        self._parse_pattern = re.compile(
            r'[ld]i[sc]t\[(.+)\]',
            re.IGNORECASE
        )
        self._vals_pattern = re.compile(
            r'(?P<name>[^#]+)(?:#(?P<description>.+)#)?:\s'
            r'(?P<type>[a-zA-Z_\[\]]+)'
            r'(?:\s=\s(?P<default>[^\]]+))?'
        )
        self._optional_pattern = re.compile(
            r'Optional\[(.+)\]'
        )

    @property
    def variables(self) -> List[str]:
        """All the parsed variable names.

        :return: Returns a list of variable names
        :rtype: List[str]
        """
        for var in self.__get_var_strings():
            yield self._vals_pattern.search(
                var
            ).groupdict()['name']

    def parse(self) -> List[Dict[str, Any]]:
        """Resolves the parameter type into attributes
        using regular expressions.

        :return: The resolved parameters.
        :rtype: List[Dict[str, Any]]
        """
        if self.name == 'mentions':
            return [{
                'name': 'user-mentions',
                'type': OptionTypes.MENTION.value,
                'description': 'Users to mention',
                'required': 'Optional' not in str(self.type)
            }]
        if self.name not in ('args', 'kwargs'):
            return []
        parsed_list = []
        variables = self.__get_var_strings()
        for var in variables:
            parsed = self._vals_pattern.search(var).groupdict()
            parsed['required'] = 'Optional' not in parsed['type']
            parsed['type'] = OptionTypes[
                self._optional_pattern.sub(r'\1', parsed['type'])
            ].value
            parsed['description'] = parsed.get(
                'description'
            ) or 'Please enter a value.'
            if parsed.get('default') is not None:
                if parsed['type'] == 4:
                    parsed['default'] = int(parsed['default'])
                elif parsed['type'] == 10:
                    parsed['default'] = float(parsed['default'])
                elif parsed['type'] == 5:
                    parsed['default'] = parsed['default'] == 'True'
                parsed['description'] += f" Default is {parsed['default']}."
            parsed_list.append(parsed)
        return parsed_list

    def __get_var_strings(self):
        match_ = self._parse_pattern.search(self.type)
        if match_ is None:
            raise ValueError('Invalid Parameter.')
        yield from match_.group(1).split(', ')


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
        self._patterns = [
            re.compile(
                r'^\.\. (?P<directive>\w+)\:\:(?:\s(?P<argument>.+))?$'
            ),
            re.compile(
                r':(?P<option>\w+):(?:\s(?P<value>.+))?$'
            ),
            re.compile(
                r':param\s(?P<name>[^:]+):(?:\s(?P<value>.+))?$'
            ),
            re.compile(
                r':type\s(?P<name>[^:]+):(?:\s(?P<value>.+))?$'
            ),
            re.compile(r'\s{4}[^\*\d]+')
        ]
        self._tab_space = 8
        #: Meta :class:`~scripts.helpers.parsers.Directive`
        #:
        #: .. tip::
        #:
        #:     There's usually only one Meta directive per docstring.
        self.meta = None
        #: All the parsed :class:`~scripts.helpers.parsers.Directive`.
        self.directives = []
        #: All the parsed :class:`~scripts.helpers.parsers.Param`.
        self.params = {}
        #: Rubric sections containing child
        #:  :class:`~scripts.helpers.parsers.Directive`.
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
                param, type_
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
            elif type_:
                type_ = type_.groupdict()
                self.params[type_['name']].type = type_['value']
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
        if not line:
            return None
        return " ".join(line.split())

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
