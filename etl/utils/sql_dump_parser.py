from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


INSERT_PATTERN = re.compile(
    r"INSERT\s+INTO\s+`?(?P<table>[A-Za-z0-9_]+)`?\s*(?:\((?P<columns>.*?)\))?\s*VALUES\s*(?P<values>.*?);",
    flags=re.IGNORECASE | re.DOTALL,
)


@dataclass
class ParsedTableData:
    columns: list[str] | None
    rows: list[list[Any]]


def parse_sql_dump(sql_text: str, target_tables: set[str] | None = None) -> dict[str, ParsedTableData]:
    parsed: dict[str, ParsedTableData] = {}

    for match in INSERT_PATTERN.finditer(sql_text):
        table = match.group("table").strip("` ").lower()
        if target_tables and table not in target_tables:
            continue

        columns_raw = match.group("columns")
        values_raw = match.group("values")

        columns = parse_columns(columns_raw) if columns_raw else None
        rows = parse_values_block(values_raw)

        if table not in parsed:
            parsed[table] = ParsedTableData(columns=columns, rows=[])

        if parsed[table].columns is None and columns:
            parsed[table].columns = columns

        parsed[table].rows.extend(rows)

    return parsed


def parse_columns(columns_raw: str) -> list[str]:
    cols = []
    for token in columns_raw.split(","):
        col = token.strip().strip("`").strip()
        if col:
            cols.append(col)
    return cols


def parse_values_block(values_raw: str) -> list[list[Any]]:
    rows: list[list[Any]] = []
    depth = 0
    in_string = False
    escaped = False
    current = []

    for char in values_raw:
        if in_string:
            current.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == "'":
                in_string = False
            continue

        if char == "'":
            in_string = True
            current.append(char)
            continue

        if char == "(":
            if depth > 0:
                current.append(char)
            depth += 1
            continue

        if char == ")":
            depth -= 1
            if depth == 0:
                row = "".join(current)
                rows.append(parse_row_values(row))
                current = []
            else:
                current.append(char)
            continue

        if depth > 0:
            current.append(char)

    return rows


def parse_row_values(row_raw: str) -> list[Any]:
    values: list[str] = []
    in_string = False
    escaped = False
    current: list[str] = []

    for char in row_raw:
        if in_string:
            current.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == "'":
                in_string = False
            continue

        if char == "'":
            in_string = True
            current.append(char)
            continue

        if char == ",":
            values.append("".join(current))
            current = []
            continue

        current.append(char)

    if current:
        values.append("".join(current))

    return [sql_token_to_python(token) for token in values]


def sql_token_to_python(token: str) -> Any:
    value = token.strip()

    if value.upper() in {"NULL", "\\N"}:
        return None

    if value.upper() == "TRUE":
        return True

    if value.upper() == "FALSE":
        return False

    if value.startswith("'") and value.endswith("'"):
        return decode_sql_string(value[1:-1])

    if re.fullmatch(r"-?\d+", value):
        try:
            return int(value)
        except ValueError:
            return value

    if re.fullmatch(r"-?\d+\.\d+", value):
        try:
            return float(value)
        except ValueError:
            return value

    return value


def decode_sql_string(raw_value: str) -> str:
    out = raw_value
    out = out.replace("\\'", "'")
    out = out.replace('\\"', '"')
    out = out.replace("\\r", "\r")
    out = out.replace("\\n", "\n")
    out = out.replace("\\t", "\t")
    out = out.replace("\\0", "\0")
    out = out.replace("\\\\", "\\")
    out = out.replace("''", "'")
    return out
