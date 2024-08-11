import os
import sys
import importlib
import paramiko
import socket
import threading
from rich.console import Console
from rich.text import Text
from io import StringIO
from hometerm.command import Command
import re

COMMANDS_DIR = os.environ.get("TERM_COMMANDS_DIR", "./commands")
TERM_KEYFILE = os.environ.get("TERM_KEYFILE", "./id_rsa")

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


def load_commands(root_directory: str):
    commands, imported_classes, import_errors = [], [], []

    for root, dirs, files in os.walk(root_directory):
        if os.path.isabs(root):
            parent_dir, last_parent_directory = os.path.dirname(root), os.path.basename(
                root
            )

        else:
            parent_dir, last_parent_directory = os.getcwd(), root
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)
        # Import classes from Python Files
        for filename in files:
            if filename.endswith(".py"):
                module_name = os.path.splitext(filename)[
                    0
                ]  # Remove the file extension to get the module name
                last_parent_directory = (
                    last_parent_directory.replace("..\\", "")
                    .replace("../", "")
                    .replace(".\\", "")
                    .replace("./", "")
                )  # Remove relative path prefix
                last_parent_directory = last_parent_directory.replace(
                    "\\", "."
                ).replace(
                    "/", "."
                )  # Replace path separators with dots

                module_import_path = (
                    f"{last_parent_directory}.{module_name}"  # Build module import path
                )

                try:
                    if module_import_path in sys.modules:
                        del sys.modules[module_import_path]

                    module_object = importlib.import_module(module_import_path)

                    # Iterate over items in the module_object
                    for attribute_name in dir(module_object):
                        # Get the attributes from the module_object
                        attribute = getattr(module_object, attribute_name)

                        # Check if it's a class and append to list
                        if (
                            isinstance(attribute, type)
                            and issubclass(attribute, Command)
                            and "hometerm.command" not in str(attribute)
                        ):
                            imported_classes.append(attribute)
                        elif attribute_name == "commands":
                            try:
                                commands += attribute()
                            except Exception as e:
                                print(e)
                                pass

                except Exception as import_error:
                    # In case of import errors; save the import arguments and the error and continue with other files
                    import_errors.append((parent_dir, module_import_path, import_error))
    commands += [x() for x in imported_classes]
    return commands

COMMANDS = load_commands(COMMANDS_DIR)


class SSHOutput(StringIO):
    def __init__(self, channel):
        super().__init__()
        self.channel = channel
        self.ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
        self.max_chunk_size = 1000

    def write(self, text):
        if len(text) < 1000:
            self.channel.send(text.replace("\n", "\r\n"))
            return
        lines = text.split("\n")
        for line in lines:
            self._send_chunked_line(line)
            self.channel.send("\r\n")

    def _send_chunked_line(self, line):
        chunks = []
        current_chunk = ""
        current_ansi = ""

        for char in line:
            if self.ansi_escape.match(char):
                current_ansi += char
            else:
                if len(current_chunk) + len(current_ansi) + 1 > self.max_chunk_size:
                    chunks.append(current_chunk)
                    current_chunk = current_ansi + char
                else:
                    current_chunk += current_ansi + char
                current_ansi = ""

        if current_chunk:
            chunks.append(current_chunk)

        for chunk in chunks:
            self.channel.send(chunk)


class SSHOutputold(StringIO):
    def __init__(self, channel):
        super().__init__()
        self.channel = channel

    def write(self, text):
        print(len(text))
        if len(text) > 1000:
            for i in range(0, len(text), 1000):
                self.channel.send(text[i : i + 1000])
        else:
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
                self.send_rich(
                    f"Invalid command '{cmd}'. Type `help` to see available commands.\n"
                )

            self.prompt()

        self.channel.close()

    def help_text(self):
        help_text = "\nAvailable commands:\n"
        help_text = Text.assemble(
            ("exit" + "\t\t", "bold blue"), ("Exit the terminal\n", "white")
        )
        command_str = Text.assemble(
            ("help\t\t", "bold blue"), ("Show this help text", "white")
        )
        help_text = Text.assemble(help_text, command_str + "\n")

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
        transport.add_server_key(paramiko.RSAKey(filename=TERM_KEYFILE))

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
    port = int(os.environ.get("SSH_PORT", 22))
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", port))  # Listen on all interfaces, port 2022
    sock.listen(100)

    print("Listening for connections...")

    while True:
        client, addr = sock.accept()
        print(f"Got a connection from {addr}")
        client_thread = threading.Thread(target=handle_client, args=(client, addr))
        client_thread.start()


if __name__ == "__main__":
    start_server()
