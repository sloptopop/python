"""Start sloptopop, print who answered, and shut it down.

Run with ``uv run examples/hello.py``; the binary is found via SLOPTOPOP_BIN,
the package's bundled copy, or PATH.
"""

from sloptopop import Client


def main() -> None:
    """Print the server's name, version and protocol version."""
    with Client() as client:
        info = client.server_info
        print(f"{info.server_name} {info.server_version} (protocol {info.protocol_version})")


if __name__ == "__main__":
    main()
