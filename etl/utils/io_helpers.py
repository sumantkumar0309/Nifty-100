from __future__ import annotations

import re
from typing import Iterable

import numpy as np
import pandas as pd

NULL_STRINGS = {"NULL", "Null", "null", "NONE", "None", "none", "N/A", "n/a", ""}


def snake_case(value: str) -> str:
    value = value.strip().replace("%", " pct ").replace("+", " plus ")
    value = re.sub(r"[^A-Za-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value)
    return value.strip("_").lower()


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    renamed = {col: snake_case(str(col)) for col in df.columns}
    out = df.rename(columns=renamed)

    base_names = [col if col else f"col_{idx + 1}" for idx, col in enumerate(out.columns)]
    seen: dict[str, int] = {}
    unique_names: list[str] = []
    for name in base_names:
        count = seen.get(name, 0)
        if count == 0:
            unique_names.append(name)
        else:
            unique_names.append(f"{name}_{count + 1}")
        seen[name] = count + 1

    out.columns = unique_names
    return out


def normalize_nulls(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_object_dtype(out[col]):
            out[col] = out[col].apply(
                lambda x: np.nan
                if isinstance(x, str) and x.strip() in NULL_STRINGS
                else x.strip()
                if isinstance(x, str)
                else x
            )
    return out


def safe_to_numeric(series: pd.Series) -> pd.Series:
    if not pd.api.types.is_object_dtype(series):
        return pd.to_numeric(series, errors="coerce")

    cleaned = (
        series.astype(str)
        .str.replace(",", "", regex=False)
        .str.replace("%", "", regex=False)
        .str.replace("Rs", "", regex=False)
        .str.replace("₹", "", regex=False)
        .str.replace(" ", "", regex=False)
    )
    cleaned = cleaned.replace({"": np.nan, "nan": np.nan, "None": np.nan})
    return pd.to_numeric(cleaned, errors="coerce")


def first_matching_column(
    df: pd.DataFrame,
    include_keywords: Iterable[str],
    exclude_keywords: Iterable[str] | None = None,
) -> str | None:
    include = [x.lower() for x in include_keywords]
    exclude = [x.lower() for x in (exclude_keywords or [])]

    for col in df.columns:
        low = col.lower()
        if all(k in low for k in include) and not any(k in low for k in exclude):
            return col
    return None


def find_symbol_column(df: pd.DataFrame) -> str | None:
    candidates = [
        "symbol",
        "company_id",
        "companyid",
        "company_code",
        "code",
        "ticker",
        "nse_code",
    ]
    for candidate in candidates:
        if candidate in df.columns:
            return candidate
    for col in df.columns:
        if "company" in col and "id" in col:
            return col
    return None


def clean_symbol(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.upper()


def find_year_like_column(df: pd.DataFrame) -> str | None:
    candidates = ["year", "years", "year_label", "period", "fy"]
    for candidate in candidates:
        if candidate in df.columns:
            return candidate

    for col in df.columns:
        low = col.lower()
        if "year" in low or low in {"period", "fy", "date"}:
            return col
    return None
