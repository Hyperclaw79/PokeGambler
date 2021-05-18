"""
This module contains the Abstract Base Class for Commands.
It also has some useful decorators for the commands.
"""

# pylint: disable=unused-argument

from abc import ABC
from functools import wraps
from typing import List, Union

from scripts.base.models import Model
from ..helpers.utils import (
    get_embed, is_admin, is_dealer, is_owner
)


__all__ = [
    'owner_only', 'admin_only', 'dealer_only',
    'get_chan', 'maintenance', 'no_log', 'alias',
    'model', 'Commands'
]


def owner_only(func):
    '''
    Only the owners can access these commands.
    '''
    func.__dict__["owner_only"] = True
    @wraps(func)
    def wrapped(self, message, *args, **kwargs):
        if is_owner(self.ctx, message.author):
            return func(self, *args, message=message, **kwargs)
        func_name = func.__name__.replace("cmd_", self.ctx.prefix)
        self.logger.pprint(
            f'Command {func_name} can only be used by owners.',
            color="red",
            wrapped_func=func.__name__
        )
        return message.channel.send(
            embed=get_embed(
                f'Command `{func_name}` can only be used by the owner.',
                embed_type="error"
            )
        )
    return wrapped


def admin_only(func):
    '''
    Only the admins can access these commands.
    '''
    func.__dict__["admin_only"] = True
    @wraps(func)
    def wrapped(self, message, *args, **kwargs):
        if any([
            is_admin(message.author),
            is_owner(self.ctx, message.author)
        ]):
            return func(self, *args, message=message, **kwargs)
        func_name = func.__name__.replace("cmd_", self.ctx.prefix)
        self.logger.pprint(
            f'Command {func_name} can only be used by admins.',
            color="red",
            wrapped_func=func.__name__
        )
        return message.channel.send(
            embed=get_embed(
                f'Command `{func_name}` can only be used by admins.',
                embed_type="error"
            )
        )
    return wrapped


def dealer_only(func):
    '''
    Only the dealers can access these commands.
    '''
    func.__dict__["dealer_only"] = True
    @wraps(func)
    def wrapped(self, message, *args, **kwargs):
        if is_dealer(message.author):
            return func(self, *args, message=message, **kwargs)
        func_name = func.__name__.replace("cmd_", self.ctx.prefix)
        self.logger.pprint(
            f'Command {func_name} can only be used by dealers.',
            color="red",
            wrapped_func=func.__name__
        )
        return message.channel.send(
            embed=get_embed(
                f'Command `{func_name}` can only be used by dealers.',
                embed_type="error"
            )
        )
    return wrapped


def get_chan(func):
    '''
    Gets the active channel if there's one present.
    Else returns the message channel.
    '''
    @wraps(func)
    def wrapped(self, message, *args, **kwargs):
        if kwargs.get("channel", None):
            chan = kwargs["channel"]
        elif kwargs.get("chan", None):
            chan = kwargs["chan"]
        elif self.ctx.active_channels:
            chan = self.ctx.active_channels[-1]
        else:
            chan = message.channel
        kwargs.update({'chan': chan})
        return func(self, *args, message=message, **kwargs)
    return wrapped


def maintenance(func):
    '''
    Disable a broken/wip function to prevent it from affecting rest of the bot.
    '''
    func.__dict__["disabled"] = True

    @wraps(func)
    def wrapped(self, message, *args, **kwargs):
        func_name = func.__name__.replace('cmd_', '')
        self.logger.pprint(
            f"The command {func_name} is under maintenance.\n"
            "Wait for a future update to see changes.",
            timestamp=True,
            color="red"
        )
        return message.channel.send(
            embed=get_embed(
                f"The command {func_name} is under maintenance.\n"
                "Wait for a future update to see changes.",
                embed_type="error"
            )
        )
    return wrapped


def no_log(func):
    '''
    Pevents a command from being logged in the DB.
    Useful for debug related commands.
    '''
    func.__dict__["no_log"] = True

    @wraps(func)
    def wrapped(self, message, *args, **kwargs):
        return func(self, *args, message=message, **kwargs)
    return wrapped


def alias(alt_names: Union[List[str], str]):
    '''
    Add an alias to a function.
    '''
    if isinstance(alt_names, str):
        alt_names = [alt_names]

    def decorator(func):
        func.__dict__["alias"] = alt_names

        @wraps(func)
        def wrapped(self, message, *args, **kwargs):
            for name in alt_names:
                setattr(
                    self,
                    f"cmd_{name}",
                    getattr(self, func.__name__)
                )
            return func(self, *args, message=message, **kwargs)
        return wrapped
    return decorator


def model(models: Union[List[Model], Model]):
    '''
    Marks a command with list of Models it is accessing.
    '''
    if isinstance(models, Model):
        models = [models]

    def decorator(func):
        func.__dict__["models"] = models

        @wraps(func)
        def wrapped(self, message, *args, **kwargs):
            return func(self, *args, message=message, **kwargs)
        return wrapped
    return decorator


class Commands(ABC):
    '''
    The Base command class which serves as the starting point for all commands.
    Can also be used to enable or disable entire categories.
    '''
    def __init__(self, ctx, database, logger, *args, **kwargs):
        self.ctx = ctx
        self.database = database
        self.logger = logger
        self.enabled = kwargs.get('enabled', True)
        self.alias = []
        cmds = [
            getattr(self, attr)
            for attr in dir(self)
            if all([
                attr.startswith("cmd_"),
                "alias" in dir(getattr(self, attr))
            ])
        ]
        for cmd in cmds:
            for name in cmd.alias:
                self.alias.append(f"cmd_{name}")
                setattr(self, f"cmd_{name}", cmd)

    @property
    def enable(self):
        '''
        Quickly Enable a Commands Category module.
        '''
        self.enabled = True
        return self.enabled

    @property
    def disable(self):
        '''
        Quickly Disable a Commands Category module.
        '''
        self.enabled = False
        return self.enabled
