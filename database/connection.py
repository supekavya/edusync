import sqlite3
import os
from contextlib import contextmanager

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATABASE_NAME = os.path.join(BASE_DIR, "attendance.db")

@contextmanager
def get_db_connection():
    conn = sqlite3.connect(DATABASE_NAME, check_same_thread=False)
    try:
        yield conn
    finally:
        conn.close()
