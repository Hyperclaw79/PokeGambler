"""
Compilation of Discord UI Views
"""

# pylint: disable=unused-argument, no-member
# pylint: disable=too-few-public-methods

from typing import Callable, Dict, Optional

import discord


class SelectView(discord.ui.View):
    """
    A Select View that allows the user to choose a Pokemon bot.
    """
    class SelectComponent(discord.ui.Select):
        """
        A Select Component that allows the user to choose a Pokemon bot.
        """
        def __init__(self, options: Dict[str, str]):
            opts = [
                discord.SelectOption(
                    label=str(label),
                    description=str(description)
                )
                for label, description in options.items()
            ]
            super().__init__(
                placeholder="Choose the Pokebot from this list",
                min_values=1, max_values=1,
                options=opts
            )
            self.opts = options

        async def callback(self, interaction: discord.Interaction):
            """
            On Selecting a choice, execute the required function.
            """
            await interaction.response.send_message(
                f'Selected {self.values[0]}.'
            )
            self.view.result = [
                key
                for key in self.opts
                if str(key) == self.values[0]
            ][0]
            self.view.stop()

    def __init__(self, **kwargs):
        super().__init__()
        self.add_item(self.SelectComponent(**kwargs))
        self.result = None


class Confirm(discord.ui.View):
    """
    A simple View that gives us a confirmation menu.
    """
    def __init__(
        self, check: Optional[Callable] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.value = None
        self.check = check
        self.user = None

    @discord.ui.button(
        label='Confirm',
        style=discord.ButtonStyle.green
    )
    async def confirm(
        self, button: discord.ui.Button,
        interaction: discord.Interaction
    ):
        """
        When the confirm button is pressed, set the inner value to True.
        """
        if (
            self.check is not None
            and not self.check(interaction.user)
        ):
            return
        self.value = True
        self.user = interaction.user
        self.stop()
