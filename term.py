import os
import importlib
import paramiko
import socket
import threading
from rich.console import Console
from rich.text import Text
from io import StringIO
from commands import base_command
BaseCommand = base_command.BaseCommand

def message_handler(terminal):
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

def load_commands(commands_dir="./commands"):
    commands = []
    for filename in os.listdir(commands_dir):
        if filename.endswith('.py') and filename != 'base_command.py':
            module_name = filename[:-3]  # Remove .py extension
            module_path = os.path.join(commands_dir, filename)
            spec = importlib.util.spec_from_file_location(module_name, module_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            for item in dir(module):
                obj = getattr(module, item)
                if isinstance(obj, type) and issubclass(obj, BaseCommand) and obj is not BaseCommand:
                    command = obj()
                    commands.append(command)
    return commands

COMMANDS = load_commands('commands')


class SSHOutput(StringIO):
    def __init__(self, channel):
        super().__init__()
        self.channel = channel

    def write(self, text):
        self.channel.send(text.replace("\n", "\r\n"))


class SSHTerminal:
    def __init__(self, channel, commands):
        self.channel = channel
        self.console = Console(file=SSHOutput(channel), force_terminal=True)
        self.commands = commands

    def send_rich(self, text, newline=True):
        self.console.print(text)

    def prompt(self):
        self.console.print("\r\nλ ", style="bold green", end=None)

    def run(self):
        self.send_rich("Welcome to my home terminal!\n")
        self.send_rich(self.help_text())
        self.prompt()

        while True:
            cmd = ""
            while not cmd.endswith("\r") and not cmd.endswith("\n"):
                if self.channel.recv_ready():
                    char = self.channel.recv(1).decode("utf-8")
                    if char == "\x03":  # Ctrl+C
                        return
                    elif char == "\x7f":  # Backspace
                        if cmd:
                            cmd = cmd[:-1]
                            self.channel.send("\b \b")
                    else:
                        cmd += char
                        self.channel.send(char)

            cmd = cmd.strip()
            self.channel.send("\r\n")

            if cmd == "exit":
                break
            elif cmd == "help":
                self.send_rich(self.help_text())
            elif cmd in [x.name for x in self.commands]:
                for c in self.commands:
                    if c.name == cmd:
                        result = c.execute(self)
                        self.send_rich(result)
            else:
                self.send_rich(f"Invalid command '{cmd}'. Type `help` to see available commands.\n")

            self.prompt()

        self.channel.close()

    def help_text(self):
        help_text = "\nAvailable commands:\n"
        for command in self.commands:
            command_str = Text.assemble(
                (command.name + "\t\t", "bold blue"), (command.description, "white")
            )
            help_text = Text.assemble(help_text, command_str + "\n")
        return help_text


class SSHServer(paramiko.ServerInterface):
    def __init__(self):
        self.event = threading.Event()

    def check_channel_request(self, kind, chanid):
        if kind == "session":
            return paramiko.OPEN_SUCCEEDED
        return paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_auth_password(self, username, password):
        return paramiko.AUTH_SUCCESSFUL

    def check_auth_publickey(self, username, key):
        return paramiko.AUTH_SUCCESSFUL

    def get_allowed_auths(self, username):
        return "publickey,password"

    def check_channel_shell_request(self, channel):
        self.event.set()
        return True

    def check_channel_pty_request(
        self, channel, term, width, height, pixelwidth, pixelheight, modes
    ):
        return True


def handle_client(client_socket, addr):
    try:
        transport = paramiko.Transport(client_socket)
        transport.add_server_key(paramiko.RSAKey(filename="./coltermf"))

        server = SSHServer()
        transport.start_server(server=server)

        channel = transport.accept(20)
        if channel is None:
            print("No channel.")
            return

        server.event.wait(10)
        if not server.event.is_set():
            print("Client never asked for a shell")
            return

        terminal = SSHTerminal(channel, commands=COMMANDS)
        terminal.run()
    finally:
        transport.close()


def start_server():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", 2022))  # Listen on all interfaces, port 2022
    sock.listen(100)

    print("Listening for connections...")

    while True:
        client, addr = sock.accept()
        print(f"Got a connection from {addr}")
        client_thread = threading.Thread(target=handle_client, args=(client, addr))
        client_thread.start()


if __name__ == "__main__":
    start_server()
