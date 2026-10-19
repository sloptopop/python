# sloptopop (Python)

Python client for the `sloptopop` binary: it starts `sloptopop serve --stdio`
and talks JSON-RPC to it. No runtime dependencies; Python 3.14+.

- Protocol, CLI and conformance suite (shared by every language):
  [sloptopop/cli](https://github.com/sloptopop/cli) —
  [PROTOCOL.md](https://github.com/sloptopop/cli/blob/main/PROTOCOL.md),
  [docs/](https://github.com/sloptopop/cli/tree/main/docs),
  [conformance/](https://github.com/sloptopop/cli/tree/main/conformance).
- Python-specific tooling, quality gate and limitations:
  [LANGUAGE.md](LANGUAGE.md).

## Install

```sh
uv add sloptopop        # or: pip install sloptopop
```

The binary is found via, in order: a path passed to `Client(...)`,
`SLOPTOPOP_BIN`, a copy bundled in the package, `sloptopop` on `PATH`.

## Usage

```python
from sloptopop import Client, RpcError

with Client() as client:  # starts the binary and sends initialize
    print(client.server_info)  # ServerInfo(server_name=..., server_version=..., protocol_version=1)
    try:
        client.request("someMethod", {"any": "params"})
    except RpcError as e:
        print(e.code, e.message, e.data)
# leaving the block sends shutdown + exit and waits for the process
```

`RpcError` is a JSON-RPC error reply; `TransportError` (and its subclass
`FramingError`) means the binary is missing, died, or broke the protocol, and
closes the client. The package also installs a `sloptopop` command that runs
the binary with the same arguments, stdio and exit code.

## Example

```sh
SLOPTOPOP_BIN=/path/to/sloptopop uv run examples/hello.py
# sloptopop 0.1.0 (protocol 1)
```

## License

Licensed under either of

- Apache License, Version 2.0 ([LICENSE-APACHE](LICENSE-APACHE) or <https://www.apache.org/licenses/LICENSE-2.0>)
- MIT license ([LICENSE-MIT](LICENSE-MIT) or <https://opensource.org/licenses/MIT>)

at your option.

Unless you explicitly state otherwise, any contribution intentionally submitted
for inclusion in the work by you, as defined in the Apache-2.0 license, shall be
dual licensed as above, without any additional terms or conditions.
