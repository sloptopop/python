"""The JSON value type shared by the codec and the client."""

type JsonValue = bool | int | float | str | list[JsonValue] | dict[str, JsonValue] | None
