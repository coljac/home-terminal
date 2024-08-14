# Home Terminal

Shamelessly copied from [https://github.com/gleich/terminal](https://github.com/gleich/terminal) and implemented in python.

This code sets up a server that listens for SSH connections and then makes available a menu of commands to serve out whatever information you wish. Think of it like a home page for the extra nerdy.

![example](docs/demo.gif)

## Deployment

Can be done with or without a container - container is probably easiest, especially given the presumably less than military grade security this afternoon's python coding has ensured.

- Clone the repo.
- Define the commands you want, as below.
- Install extra python dependencies if required for your commands.
- Run `term.py`, specifying `SSH_PORT` (default: 22) and `TERM_COMMANDS_DIR` (default: `./commands`) in the environment. Optionally, add a `TERM_WELCOME` var that points to a file to be sent on login.
- It also needs a key pair to run, generate with `ssh-keygen -t rsa -f ./id_rsa`. You can override the default with the `TERM_KEYFILE` env var.

With docker:

`docker build -t hometerm .`
`docker run hometerm -p 22:22 hometerm`

This will make a key too.

## Commands

Apart from the default `help` and `exit` commands, the rest of the options are defined at runtime from a commands directory (specified with the `TERM_COMMANDS_DIR` environment variable, default: `./commands`):

- In a `commands()` method, which returns an array of Command objects;
- In any number of `hometerm.command.Command` subclasses found.

The subclasses should initialize with a `name` and `description`, and override the `execute` method to return some text or [Rich](https://github.com/Textualize/rich) Text. The should have a constructor that takes no arguments.

For example, in the `commands/` directory you might have `commands.py`:
```python
from hometerm.command import TextCommand, ImageCommand

def commands():
    return [
        TextCommand("about", "Some info about me", "commands/about.md"),
        ImageCommand("pic", "See what I look like", "commands/col.png", size=[42, 64]),
    ]
```

and/or some class defintions like `mycommand.py`:

```python
from hometerm.command import Command

class MessageCommand(Command):
    def __init__(self):
        super().__init__("message", "Send me a message")

    def execute(self, terminal):
        terminal.send_rich("Enter your message (Press enter when done):")
        terminal.console.print("\r\n> ", style="bold yellow", end=None)
        # rest of the execution here 
```

see `command.py` for details. The main thing is to either return the output, or operate on the `terminal` object passed in, which allows extra interactivity.
