# base_command.py
class BaseCommand:
    def __init__(self, name, description):
        self.name = name
        self.description = description

    def execute(self, terminal):
        raise NotImplementedError("Subclasses must implement execute method")
