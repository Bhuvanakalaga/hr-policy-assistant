# database.py
# SQLite connection helper for the HR Assistant.
# The actual database file (hr.db) is built by import_data.py from the
# existing CSV files (employees.csv, tickets.csv, leave_requests.csv,
# grievances.csv, audit_logs.csv).

import os
import sqlite3

BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE_DIR, "data", "hr.db")


def get_connection() -> sqlite3.Connection:
    """
    Return a SQLite connection to hr.db with row access by column name.
    Raises a clear error if the DB hasn't been built yet.
    """
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(
            f"Database not found at '{DB_PATH}'. "
            "Please run import_data.py first to build hr.db from your CSV files."
        )

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn