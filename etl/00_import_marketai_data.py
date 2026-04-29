from __future__ import annotations

from pathlib import Path
import warnings

import pandas as pd

from etl.config import MARKETAI_DATA_DIR, RAW_DIR, ensure_data_dirs
from etl.utils.io_helpers import normalize_columns

pd.options.mode.copy_on_write = False
warnings.filterwarnings("ignore", category=FutureWarning, message=".*ChainedAssignmentError.*")

SOURCE_TARGET_MAP = {
    "companies_clean.csv": "companies.csv",
    "analysis_cleans.csv": "analysis.csv",
    "balancesheet_clean.csv": "balancesheet.csv",
    "profitandloss_clean.csv": "profitandloss.csv",
    "cashflow_clean.csv": "cashflow.csv",
    "prosandcons_clean.csv": "prosandcons.csv",
    "documents_clean.csv": "documents.csv",
}


def copy_marketai_to_raw(source_dir: Path) -> None:
    missing = [name for name in SOURCE_TARGET_MAP if not (source_dir / name).exists()]
    if missing:
        raise FileNotFoundError(
            "Missing expected marketAI files: " + ", ".join(missing) + f" in {source_dir}"
        )

    for source_name, target_name in SOURCE_TARGET_MAP.items():
        source_path = source_dir / source_name
        target_path = RAW_DIR / target_name

        df = pd.read_csv(source_path)
        df = normalize_columns(df).copy(deep=True)

        if "company_id" in df.columns and "symbol" not in df.columns:
            df.loc[:, "symbol"] = df["company_id"]

        if "year" in df.columns and "year_label" not in df.columns:
            df.loc[:, "year_label"] = df["year"]

        df.to_csv(target_path, index=False)
        print(f"Imported {source_name} -> {target_path} (rows={len(df)}, cols={list(df.columns)})")


def main() -> None:
    ensure_data_dirs()

    source_dir = MARKETAI_DATA_DIR
    if not source_dir.exists():
        raise FileNotFoundError(
            f"MARKETAI_DATA_DIR does not exist: {source_dir}. "
            "Set MARKETAI_DATA_DIR to your cloned repo data folder."
        )

    print(f"Source marketAI data directory: {source_dir}")
    print(f"Target raw directory: {RAW_DIR}")
    copy_marketai_to_raw(source_dir)
    print("marketAI import complete.")


if __name__ == "__main__":
    main()
