import sys, os
from rich.markdown import Markdown
from rich_pixels import Pixels

class Command:
    def __init__(self, name, description):
        self.name = name
        self.description = description

    def execute(self, terminal):
        raise NotImplementedError("Subclasses must implement execute method")

    def get_file_path(self, file_name):
        """
        Get the full path of the file in the same directory as the command file.
        Returns its argument if it's an absolute path.
        """
        if "/" not in file_name:
            module_path = os.path.dirname(os.path.abspath(sys.modules[self.__class__.__module__].__file__))
            return os.path.join(module_path, file_name)
        return file_name



class TextCommand(Command):
    def __init__(self, name, desc, text_file):
        super().__init__(name, desc)
        self.text_file = self.get_file_path(text_file)

    def execute(self, terminal):
        with open(self.text_file, "r") as f:
            about_text = f.read()
        if ".md" in self.text_file.lower():
            return Markdown(about_text)
        else:
            return about_text

class ImageCommand(Command):
    def __init__(self, name, description, image_file, size=[50, 50]):
        super().__init__(name, description)
        self.size = size
        self.image_file = self.get_file_path(image_file)

    def execute(self, terminal):
        console = terminal.console # Console()
        pixels = Pixels.from_image_path(self.image_file, resize=self.size)
        console.print(pixels)
        return ""
