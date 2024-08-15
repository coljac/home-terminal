# commands/message_command.py
from commands.base_command import BaseCommand

class MessageCommand(BaseCommand):
    def __init__(self):
        super().__init__("message", "Send me a message")

    def execute(self, terminal):
        terminal.send_rich("Enter your message (Press enter when done):")
        terminal.console.print("\r\n> ", style="bold yellow", end=None)
        
        message = ""
        while True:
            char = terminal.channel.recv(1).decode("utf-8")
            if char == "\r" or char == "\n":
                break
            elif char == "\x7f":  # Backspace
                if message:
                    message = message[:-1]
                    terminal.channel.send("\b \b")
            else:
                message += char
                terminal.channel.send(char)
        
        if message:
            with open("messages.txt", "a") as f:
                f.write(message + "\n")
            return "\nMessage saved successfully!"
        else:
            return "\nNo message entered."
