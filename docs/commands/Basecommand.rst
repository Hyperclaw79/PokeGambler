Basecommand
===========

.. automodule:: scripts.commands.basecommand

.. _Commands:
.. _Command:
.. autoclass:: scripts.commands.basecommand.Commands
    :members:

.. autofunction:: scripts.commands.basecommand.get_profile


Decorators
==========

.. rubric:: Permissions
.. autodecorator:: scripts.commands.basecommand.admin_only

.. autodecorator:: scripts.commands.basecommand.dealer_only

.. autodecorator:: scripts.commands.basecommand.owner_only

.. autodecorator:: scripts.commands.basecommand.os_only

.. rubric:: Decorators without arguments
.. autodecorator:: scripts.commands.basecommand.cache_images

.. autodecorator:: scripts.commands.basecommand.check_completion

.. autodecorator:: scripts.commands.basecommand.ctx_command

.. autodecorator:: scripts.commands.basecommand.defer

.. autodecorator:: scripts.commands.basecommand.ensure_item

.. autodecorator:: scripts.commands.basecommand.ensure_user

.. autodecorator:: scripts.commands.basecommand.maintenance

.. autodecorator:: scripts.commands.basecommand.no_log

.. autodecorator:: scripts.commands.basecommand.no_slash

.. rubric:: Decorators with arguments
.. autodecorator:: scripts.commands.basecommand.alias

.. autodecorator:: scripts.commands.basecommand.autocomplete

.. autodecorator:: scripts.commands.basecommand.cooldown

.. autodecorator:: scripts.commands.basecommand.needs_ticket

.. autodecorator:: scripts.commands.basecommand.model