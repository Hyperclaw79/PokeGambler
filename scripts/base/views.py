"""
Compilation of Discord UI Views
"""

# pylint: disable=unused-argument, no-member
# pylint: disable=too-few-public-methods

from typing import Callable, Dict, Optional

import discord


class SelectView(discord.ui.View):
    """
    A Select View that allows the user to choose an option.
    """
    class SelectComponent(discord.ui.Select):
        """
        A Select Component that allows the user to choose an option.
        """
        def __init__(self, heading: str, options: Dict[str, str]):
            opts = [
                discord.SelectOption(
                    label=str(label),
                    description=str(description)
                )
                for label, description in options.items()
            ]
            super().__init__(
                placeholder=heading,
                min_values=1, max_values=1,
                options=opts
            )
            self.opts = options

        async def callback(self, interaction: discord.Interaction):
            """
            On Selecting a choice, execute the required function.
            """
            if not self.view.no_response:
                await interaction.response.send_message(
                    f'Selected {self.values[0]}.',
                    ephemeral=True
                )
            self.view.result = [
                key
                for key in self.opts
                if str(key) == self.values[0]
            ][0]
            self.view.stop()

    def __init__(self, no_response=False, **kwargs):
        super().__init__()
        self.add_item(self.SelectComponent(**kwargs))
        self.no_response = no_response
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
        label="️️️️✔️",
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


class LinkView(discord.ui.View):
    """
    A View that allows the user to visit a link.
    """
    def __init__(
        self, url: str,
        emoji: str, **kwargs
    ):
        super().__init__(**kwargs)
        self.add_item(
            discord.ui.Button(
                label='Invite Me',
                url=url,
                emoji=emoji
            )
        )
