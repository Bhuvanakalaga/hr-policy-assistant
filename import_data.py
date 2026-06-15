# import_data.py
# One-time script to import your existing CSV files into hr.db (SQLite).
#
# Run this ONCE (and again whenever your CSVs change):
#     python import_data.py
#
# Reads (from data/, your existing files - not generated):
#     employees.csv      (key column: emp_id)
#     tickets.csv        (key column: employee_id)
#     leave_requests.csv (key column: employee_id)
#     grievances.csv     (key column: employee_id)
#     audit_logs.csv      (key column: employee_id)
#
# Note: employees.csv uses "emp_id" while the other tables use "employee_id".
# Both are normalised to uppercase/stripped for consistent lookups.
# This script does NOT create or fabricate any data - it only loads your
# existing CSVs into SQLite tables of the same name.

import os
import sqlite3
import pandas as pd

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "hr.db")

# table_name -> csv filename
CSV_TABLES = {
    "employees": "employees.csv",
    "tickets": "tickets.csv",
    "leave_requests": "leave_requests.csv",
    "grievances": "grievances.csv",
    "audit_logs": "audit_logs.csv",
}

# Columns to normalise (uppercase + strip) per table, if present
ID_COLUMNS = ["emp_id", "employee_id"]


def import_all():
    conn = sqlite3.connect(DB_PATH)

    for table_name, csv_file in CSV_TABLES.items():
        csv_path = os.path.join(DATA_DIR, csv_file)

        if not os.path.exists(csv_path):
            print(f"[SKIP] {csv_file} not found in data/ - table '{table_name}' not created.")
            continue

        df = pd.read_csv(csv_path, dtype=str).fillna("")

        for col in ID_COLUMNS:
            if col in df.columns:
                df[col] = df[col].str.upper().str.strip()

        df.to_sql(table_name, conn, if_exists="replace", index=False)
        print(f"[OK] Imported {len(df)} rows into '{table_name}' from {csv_file}")

    # Helpful indexes for employee-scoped lookups
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tickets_emp ON tickets(employee_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_grievances_emp ON grievances(employee_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_leave_requests_emp ON leave_requests(employee_id)")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    conn.close()
    print(f"\nDatabase ready at: {DB_PATH}")


if __name__ == "__main__":
    print("Building hr.db from existing CSV files...")
    import_all()
    print("Done.")