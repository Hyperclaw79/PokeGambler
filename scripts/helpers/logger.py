"""
Custom Logger Module.
"""

# pylint: disable=unused-argument

import re
from datetime import datetime
from typing import Optional

import chalk
from colorama import init

init()  # Initialize Colorama


class CustomLogger:
    '''
    A simple Logger which has the main purpose of colorifying outputs.
    Barebones implementation without importing from the Logging module.
    '''
    def __init__(self, error_log_path: str):
        formats = [
            "white", "green",
            "yellow", "red",
            "blue", "bold"
        ]
        self.color_codings = {
            fmt: getattr(chalk, fmt)
            for fmt in formats
        }
        self.error_log_path = error_log_path
        # Pattern to delete the color codes while logging into file.
        self.ansi_escape = re.compile(
            r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])'
        )

    def pprint(
        self, text: str, *args,
        timestamp: bool = True,
        **kwargs
    ):
        '''
        Wraps the text and prints it to Stdout.
        In case of an error (red), logs it to error.log
        '''
        if kwargs and kwargs.get("color") == "red":
            func_name = kwargs.get("wrapped_func")
            with open(self.error_log_path, 'a', encoding='utf-8') as err_log:
                err_log.write(
                    f"[{datetime.now().strftime('%X %p')}] <{func_name}>"
                    f" {self.ansi_escape.sub('', text)}\n"
                )
        if timestamp:
            text = f"[{datetime.now().strftime('%X %p')}] {text}"
        colored = self.wrap(text, *args, **kwargs)
        print(colored)

    def wrap(
        self, text: str, *args,
        color: Optional[str] = None,
        **kwargs
    ):
        '''
        Wraps the text based on the color and returns it.
        Can handle a list of colors as well.
        '''
        if color and isinstance(color, list):
            for fmt in color:
                func = self.color_codings.get(fmt, chalk.white)
                text = func(text)
            return text
        func = self.color_codings.get(color, chalk.white)
        return func(text)
