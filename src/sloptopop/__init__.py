"""Python client for the sloptopop binary.

Start a session with :class:`Client`; see ``PROTOCOL.md`` in the
``sloptopop/cli`` repository for the wire protocol.
"""

from sloptopop._binary import ENV_VAR, find_binary
from sloptopop._client import CLIENT_NAME, PROTOCOL_VERSION, Client, ServerInfo
from sloptopop._errors import FramingError, RpcError, SloptopopError, TransportError
from sloptopop._json import JsonValue
from sloptopop._version import __version__

__all__ = [
    "CLIENT_NAME",
    "ENV_VAR",
    "PROTOCOL_VERSION",
    "Client",
    "FramingError",
    "JsonValue",
    "RpcError",
    "ServerInfo",
    "SloptopopError",
    "TransportError",
    "__version__",
    "find_binary",
]
