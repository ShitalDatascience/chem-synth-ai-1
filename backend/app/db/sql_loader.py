from pathlib import Path

SQL_DIR = Path(__file__).resolve().parent / "queries"

def _load_sql(filename: str) -> str:
    file_path = SQL_DIR / filename

    if not file_path.exists():
        raise FileNotFoundError(f"SQL file not found: {file_path}")

    return file_path.read_text()