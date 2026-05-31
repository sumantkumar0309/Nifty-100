#!/usr/bin/env python3
"""Extract raw Nifty 100 tables from a MariaDB SQL dump into CSV files."""

from __future__ import annotations

import argparse
import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

import pandas as pd

TARGET_TABLES: Sequence[str] = (
    "companies",
    "analysis",
    "balancesheet",
    "profitandloss",
    "cashflow",
    "prosandcons",
    "documents",
)

INSERT_PATTERN = re.compile(
    r"INSERT\\s+INTO\\s+`?(?P<table>[A-Za-z0-9_]+)`?\\s*(?:\\((?P<columns>.*?)\\))?\\s*VALUES\\s*(?P<values>.*)\\s*;\\s*$",
    re.IGNORECASE | re.DOTALL,
)

CREATE_TABLE_TEMPLATE = r"CREATE\\s+TABLE\\s+`?{table}`?\\s*\\((?P<body>.*?)\\)\\s*(?:ENGINE|COMMENT|;|PARTITION)"

MYSQL_ESCAPE_MAP = {
    "0": "\\0",
    "b": "\\b",
    "n": "\\n",
    "r": "\\r",
    "t": "\\t",
    "Z": "\\x1a",
    "'": "'",
    '"': '"',
    "\\\\": "\\\\",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sql-file",
        default="data/source/scriptticker.sql",
        help="Path to SQL dump file.",
    )
    parser.add_argument(
        "--output-dir",
        default="data/raw",
        help="Directory where extracted CSV files are stored.",
    )
    parser.add_argument(
        "--encoding",
        default="utf-8",
        help="Encoding used to read the SQL dump.",
    )
    return parser.parse_args()


def load_sql_text(sql_file: Path, encoding: str) -> str:
    if not sql_file.exists():
        raise FileNotFoundError(f"SQL dump not found: {sql_file}")
    return sql_file.read_text(encoding=encoding, errors="replace")


def extract_create_table_columns(sql_text: str, table: str) -> List[str]:
    pattern = re.compile(CREATE_TABLE_TEMPLATE.format(table=re.escape(table)), re.IGNORECASE | re.DOTALL)
    match = pattern.search(sql_text)
    if not match:
        return []

    columns: List[str] = []
    for line in match.group("body").splitlines():
        line = line.strip()
        if not line.startswith("`"):
            continue
        col_match = re.match(r"`([^`]+)`\\s+", line)
        if col_match:
            columns.append(col_match.group(1).strip())
    return columns


def iter_insert_statements(sql_text: str) -> Iterator[str]:
    haystack = sql_text.upper()
    needle = "INSERT INTO"
    pos = 0

    while True:
        start = haystack.find(needle, pos)
        if start == -1:
            return

        in_quote = False
        is_escaped = False
        i = start

        while i < len(sql_text):
            ch = sql_text[i]

            if in_quote:
                if is_escaped:
                    is_escaped = False
                elif ch == "\\\\":
                    is_escaped = True
                elif ch == "'":
                    in_quote = False
            else:
                if ch == "'":
                    in_quote = True
                elif ch == ";":
                    yield sql_text[start : i + 1]
                    pos = i + 1
                    break
            i += 1
        else:
            yield sql_text[start:]
            return


def split_row_blobs(values_blob: str) -> List[str]:
    rows: List[str] = []
    in_quote = False
    is_escaped = False
    depth = 0
    current: List[str] = []

    for ch in values_blob:
        if in_quote:
            current.append(ch)
            if is_escaped:
                is_escaped = False
            elif ch == "\\\\":
                is_escaped = True
            elif ch == "'":
                in_quote = False
            continue

        if ch == "'":
            in_quote = True
            current.append(ch)
            continue

        if ch == "(":
            if depth > 0:
                current.append(ch)
            depth += 1
            continue

        if ch == ")":
            depth -= 1
            if depth == 0:
                rows.append("".join(current))
                current = []
            else:
                current.append(ch)
            continue

        if depth > 0:
            current.append(ch)

    return rows


def split_fields(row_blob: str) -> List[str]:
    fields: List[str] = []
    current: List[str] = []
    in_quote = False
    is_escaped = False

    for ch in row_blob:
        if in_quote:
            current.append(ch)
            if is_escaped:
                is_escaped = False
            elif ch == "\\\\":
                is_escaped = True
            elif ch == "'":
                in_quote = False
            continue

        if ch == "'":
            in_quote = True
            current.append(ch)
            continue

        if ch == ",":
            fields.append("".join(current).strip())
            current = []
            continue

        current.append(ch)

    fields.append("".join(current).strip())
    return fields


def _mysql_unescape(text: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        escaped_char = match.group(1)
        return MYSQL_ESCAPE_MAP.get(escaped_char, escaped_char)

    text = re.sub(r"\\\\(.)", _replace, text)
    return text.replace("''", "'")


def parse_value_token(token: str) -> Optional[str]:
    token = token.strip()
    if not token or token.upper() == "NULL":
        return None

    if token.startswith("'") and token.endswith("'"):
        return _mysql_unescape(token[1:-1])

    return token


def parse_columns_list(raw_columns: Optional[str]) -> List[str]:
    if not raw_columns:
        return []
    return [segment.strip().strip("`") for segment in raw_columns.split(",")]


def parse_insert_statement(statement: str) -> Tuple[Optional[str], List[str], List[List[Optional[str]]]]:
    match = INSERT_PATTERN.match(statement.strip())
    if not match:
        return None, [], []

    table = match.group("table").strip()
    columns = parse_columns_list(match.group("columns"))
    row_blobs = split_row_blobs(match.group("values"))
    rows = [[parse_value_token(token) for token in split_fields(blob)] for blob in row_blobs]

    return table, columns, rows


def align_row_to_columns(
    source_columns: List[str],
    row_values: List[Optional[str]],
    canonical_columns: List[str],
) -> List[Optional[str]]:
    row_map = {source_columns[idx]: row_values[idx] for idx in range(min(len(source_columns), len(row_values)))}
    return [row_map.get(col) for col in canonical_columns]


def extract_tables(sql_text: str) -> Dict[str, pd.DataFrame]:
    create_table_columns = {table: extract_create_table_columns(sql_text, table) for table in TARGET_TABLES}
    canonical_columns: Dict[str, List[str]] = {}
    table_rows: Dict[str, List[List[Optional[str]]]] = defaultdict(list)

    for statement in iter_insert_statements(sql_text):
        table, statement_columns, statement_rows = parse_insert_statement(statement)
        if table is None or table not in TARGET_TABLES:
            continue

        source_columns = statement_columns or create_table_columns.get(table, [])
        if not source_columns:
            logging.warning("Skipping table %s because columns are unavailable.", table)
            continue

        if table not in canonical_columns:
            canonical_columns[table] = create_table_columns.get(table) or source_columns

        for row_values in statement_rows:
            if len(row_values) != len(source_columns):
                if len(row_values) < len(source_columns):
                    row_values = row_values + [None] * (len(source_columns) - len(row_values))
                else:
                    row_values = row_values[: len(source_columns)]
            aligned_row = align_row_to_columns(source_columns, row_values, canonical_columns[table])
            table_rows[table].append(aligned_row)

    extracted: Dict[str, pd.DataFrame] = {}
    for table in TARGET_TABLES:
        cols = canonical_columns.get(table) or create_table_columns.get(table, [])
        extracted[table] = pd.DataFrame(table_rows.get(table, []), columns=cols)
    return extracted


def write_raw_csvs(extracted_tables: Dict[str, pd.DataFrame], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    for table, df in extracted_tables.items():
        output_file = output_dir / f"{table}.csv"
        df.to_csv(output_file, index=False)
        print(f"[{table}] rows={len(df)} columns={list(df.columns)}")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = parse_args()

    sql_file = Path(args.sql_file)
    output_dir = Path(args.output_dir)

    sql_text = load_sql_text(sql_file, args.encoding)
    extracted_tables = extract_tables(sql_text)
    write_raw_csvs(extracted_tables, output_dir)


if __name__ == "__main__":
    main()
