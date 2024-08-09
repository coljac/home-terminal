# commands/about_command.py
from commands.base_command import BaseCommand
from rich.text import Text
from rich.markdown import Markdown

class AboutCommand(BaseCommand):
    def __init__(self):
        super().__init__("about", "About me")

    def execute(self, terminal):
        with open("about.md", "r") as f:
            about_text = f.read()
        return Markdown(about_text)


