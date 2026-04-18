import sqlite3
from werkzeug.security import generate_password_hash

DB_PATH = "meditech.db"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password_hash TEXT,
            full_name TEXT,
            address TEXT,
            phone TEXT,
            role TEXT,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT,
            date_of_birth TEXT,
            gender TEXT,
            phone TEXT,
            address TEXT,
            created_at TEXT,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER,
            created_by_user_id INTEGER,
            appointment_date TEXT,
            appointment_time TEXT,
            status TEXT DEFAULT 'scheduled',
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS medical_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER,
            user_id INTEGER,
            visit_date TEXT,
            dx TEXT,
            chief_complaint TEXT,
            present_illness TEXT,
            vitals TEXT,
            labs_requested TEXT,
            lab_results TEXT,
            special_notes TEXT,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS patient_illnesses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER,
            illness TEXT,
            date_added TEXT
        );

        CREATE TABLE IF NOT EXISTS prescriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            medical_record_id INTEGER,
            med_name TEXT,
            strength TEXT,
            dosage TEXT,
            duration_days INTEGER,
            continue_flag INTEGER DEFAULT 0,
            prescribed_date TEXT
        );
    """)

    # Migrations for pre-existing DBs: add new columns if missing
    for col in ("chief_complaint", "present_illness"):
        try:
            cur.execute(f"ALTER TABLE medical_records ADD COLUMN {col} TEXT")
        except sqlite3.OperationalError:
            pass

    conn.commit()
    conn.close()
    print("meditech.db initialised with all tables.")


if __name__ == "__main__":
    init_db()
