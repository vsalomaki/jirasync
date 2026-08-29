class JirasyncError(Exception):
    """Base for every error this package raises deliberately."""


class ConfigError(JirasyncError):
    """A configuration file is malformed, or disagrees with another file.

    Carries the offending path so a message can name the file the operator has
    to open, which a bare pydantic error does not.
    """

    def __init__(self, message: str, *, path: object = None) -> None:
        self.path = path
        super().__init__(f"{path}: {message}" if path else message)


class RoleError(ConfigError):
    """A command was invoked on a deployment whose role does not permit it."""
