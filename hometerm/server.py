import os
import time
import sys
import importlib
import paramiko
import socket
import threading
import weakref
import gc
from rich.console import Console
from rich.text import Text
import logging
sys.path.append(".")
from hometerm.command import Command

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CONNECTION_LIMIT = 20
MAX_ERRORS = 3

COMMANDS_DIR = os.environ.get("TERM_COMMANDS_DIR", "./commands")
TERM_KEYFILE = os.environ.get("TERM_KEYFILE", "./id_rsa")

class SSHOutput:
    """File-like object that sends output over an SSH channel."""
    def __init__(self, channel):
        self.channel = channel
        self._closed = False
        self.max_chunk_size = 1000

    def write(self, text):
        if self._closed or not self.channel:
            return
        if len(text) < self.max_chunk_size:
            self.channel.send(text.replace("\n", "\r\n"))
            return
        lines = text.split("\n")
        for i, line in enumerate(lines):
            if len(line) > self.max_chunk_size:
                for j in range(0, len(line), self.max_chunk_size):
                    self.channel.send(line[j:j + self.max_chunk_size])
            else:
                self.channel.send(line)
            if i < len(lines) - 1:
                self.channel.send("\r\n")

    def flush(self):
        pass

    def isatty(self):
        return True

    def close(self):
        self._closed = True
        self.channel = None

    @property
    def closed(self):
        return self._closed


class SSHTerminal:
    def __init__(self, channel, commands, addr=None):
        self.channel = channel
        self.output = SSHOutput(channel)
        self.console = Console(file=self.output, force_terminal=True)
        self.commands = commands
        self.addr = addr
        self.consecutive_errors = 0

    def send_rich(self, text, newline=True):
        self.console.print(text)

    def prompt(self):
        self.console.print("\r\nλ ", style="bold green", end=None)

    def run(self):
        welcome_message = "Welcome to my home terminal!\n"
        if "TERM_WELCOME" in os.environ:
            with open(os.environ['TERM_WELCOME'], 'r') as f:
                welcome_message = Text.from_ansi(f.read())
        self.send_rich(welcome_message)
        self.send_rich(self.help_text())
        self.prompt()

        while True:
            if self.consecutive_errors > MAX_ERRORS: # Bot? Booted!
                self.send_rich(Text("Too many errors. Exiting...", "bold red"))
                break
            cmd = ""
            while not cmd.endswith("\r") and not cmd.endswith("\n"):
                if self.channel.recv_ready():
                    data = self.channel.recv(1)
                    if not data:  # Client disconnected
                        return
                    char = data.decode("utf-8")
                    if char in ("\x03", "\x04"):  # Ctrl+C, Ctrl+D
                        return
                    elif char == "\x7f":  # Backspace
                        if cmd:
                            cmd = cmd[:-1]
                            self.channel.send("\b \b")
                    else:
                        cmd += char
                        self.channel.send(char)
                else:
                    time.sleep(0.05)

            cmd = cmd.strip().lower()
            self.channel.send("\r\n")

            if cmd == "exit":
                break
            elif cmd == "help":
                self.consecutive_errors = 0
                self.send_rich(self.help_text())
            elif cmd in [x.name for x in self.commands]:
                self.consecutive_errors = 0
                for c in self.commands:
                    if c.name == cmd:
                        try:
                            result = c.execute(self)
                            self.send_rich(result)
                        except Exception as e:
                            logger.error(f"Error executing command {cmd}: {e}")
                            self.send_rich(Text("Oops. Error!", "bold red"))
            else:
                self.consecutive_errors += 1
                logger.info(f"Invalid command '{cmd}' by {self.addr}") # Gather bot info
                self.send_rich(
                    f"Invalid command '{cmd}'. Type `help` to see available commands.\n"
                )

            self.prompt()

        self.cleanup()
    
    def cleanup(self):
        try:
            if self.channel:
                self.channel.close()
            if self.output:
                self.output.close()
            self.console = None
            self.output = None
            self.channel = None
            self.commands = None
        except:
            pass

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

class TerminalServer(object):

    def __init__(self):
        self.active_connections = 0
        self.connection_lock = threading.Lock()
        self.commands = []
        self.client_threads = weakref.WeakSet()
        self.running = True
        self.cleanup_thread = threading.Thread(target=self._cleanup_dead_threads, daemon=True)
        self.cleanup_thread.start()
        self.load_commands(COMMANDS_DIR)

    def load_commands(self, root_directory: str):
        self.commands = []  # Clear existing commands
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
                        # Don't delete modules, just reload them
                        if module_import_path in sys.modules:
                            module_object = importlib.reload(sys.modules[module_import_path])
                        else:
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
        self.commands += commands

    def handle_client(self, client_socket, addr):
        transport = None
        terminal = None
        try:
            with self.connection_lock:
                if self.active_connections >= CONNECTION_LIMIT:
                    logger.warning(f"Connection limit reached. Closing connection from {addr}")
                    client_socket.close()
                    return
                self.active_connections += 1
            logger.info("Got a connection from %s" % str(addr))

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

            terminal = SSHTerminal(channel, commands=self.commands, addr=addr)
            terminal.run()
        except Exception as e:
            logger.error(f"Error handling client {addr}: {e}")
        finally:
            with self.connection_lock:
                self.active_connections -= 1
            
            # Cleanup in reverse order
            if terminal:
                terminal.cleanup()
            if transport:
                transport.close()
            if client_socket:
                try:
                    client_socket.close()
                except:
                    pass
            
            # Force garbage collection
            gc.collect()
            logger.info("Connection from %s closed" % str(addr))

    def start(self):
        port = int(os.environ.get("SSH_PORT", 22))
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("0.0.0.0", port)) 
        sock.settimeout(1.0)  
        sock.listen(100)

        print("Listening for connections...")

        while True:
            try:
                client, addr = sock.accept()
                logger.info(f"Got a connection from {addr}")
                client_thread = threading.Thread(target=self.handle_client, args=(client, addr), daemon=True)
                self.client_threads.add(client_thread)
                client_thread.start()
            except socket.timeout:
                continue
            except Exception as e:
                logger.warn(f"Error accepting connection: {e}")


    def _cleanup_dead_threads(self):
        """Periodically clean up dead threads"""
        while self.running:
            time.sleep(30)  # Check every 30 seconds
            dead_threads = [t for t in list(self.client_threads) if not t.is_alive()]
            for thread in dead_threads:
                try:
                    thread.join(timeout=1)
                except:
                    pass
            gc.collect()
    
    def shutdown(self):
        """Graceful shutdown"""
        self.running = False
        # Wait for all client threads to finish
        for thread in list(self.client_threads):
            if thread.is_alive():
                thread.join(timeout=5)

if __name__ == "__main__":
    server = TerminalServer()
    try:
        server.start()
    except KeyboardInterrupt:
        server.shutdown()
