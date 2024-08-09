import paramiko
import socket
import threading

# from prompt_toolkit import PromptSession
# from prompt_toolkit.patch_stdout import patch_stdout
# from prompt_toolkit.input import PipeInput, create_pipe_input
# from prompt_toolkit.output import DummyOutput
from rich.console import Console
from rich.text import Text
from io import StringIO


class Command(object):
    def __init__(self, name, description, function):
        self.name = name
        self.description = description
        self.function = function


COMMANDS = [
    Command("about", "About me", lambda: "I'm great"),
]


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

    def run(self):
        # text.stylize("bold magenta", 0, 6)
        # self.send_rich(text)
        # self.channel.send("\033[1;34mAAAAAAbout me...\033[0m\r\n")
        # text = Text.from_ansi("\033[1mHello, World!\033[0m")
        # self.send_rich(text)
        # text = Text.assemble(("Hello", "bold magenta"), " World!")
        # self.send_rich(text)

        # self.channel.send("Welcome to the terminal!\r\n")
        # self.channel.send(self.help_text())
        # self.channel.send("\r\nλ ")
        self.send_rich("Welcome to the terminal!\n")
        self.send_rich(self.help_text())

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
                        self.send_rich(c.function())
            # elif command == "help":
            # self.channel.send(self.help_text())
            # elif command in ["clear", "c"]:
            # self.channel.send("\033[2J\033[H")
            # elif command == "about":
            # self.about()
            # elif command == "workouts":
            # self.workouts()
            # elif command == "projects":
            # self.projects()
            # elif command == "games":
            # self.games()
            elif cmd == "":
                pass
            else:
                self.channel.send(
                    f"\nInvalid command '{cmd}'. Type `help` to see available commands.\n\n"
                )

            # self.channel.send(
            # Color("bold green").get_ansi_codes() + "Hello, World!\033[0m"
            # )
            self.console.print("\r\nλ ", style="bold green", end=None)
            # self.send_rich(Text("λ ", "bold green"), newline=False)
        self.channel.close()

    def help_text(self):
        help_text = "\nAvailable commands:\n"
        for command in self.commands:
            command_str = Text.assemble(
                (command.name + "\t\t", "bold blue"), (command.description, "white")
            )
            help_text = Text.assemble(help_text, command_str)
        return help_text
        return """
Available commands:\r
about     a little about myself\r
workouts  my recent workouts from Strava\r

projects  recent projects I've worked on from GitHub
games     games I've recently played on Steam

help      displays this help table
exit      exit out of terminal
clear     clear the terminal
"""

    def about(self):
        self.channel.send("About me...\r\n")

    def workouts(self):
        self.channel.send("Recent workouts...\r\n")

    def projects(self):
        self.channel.send("Recent projects...\r\n")

    def games(self):
        self.channel.send("Recently played games...\r\n")


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
        transport.add_server_key(paramiko.RSAKey(filename="./colterm"))

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
