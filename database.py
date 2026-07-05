import sqlite3
import pandas as pd

DB_NAME = "highway_bills.db"

def init_db():
    """Database එක සහ Table එක නිර්මාණය කිරීම"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            vehicle_no TEXT,
            route TEXT,
            vehicle_type TEXT,
            amount REAL,
            status TEXT
        )
    ''')
    conn.commit()
    conn.close()

def add_record(date, vehicle_no, route, vehicle_type, amount, status):
    """අලුත් රෙකෝඩ් එකක් Database එකට එකතු කිරීම"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO bills (date, vehicle_no, route, vehicle_type, amount, status)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (date, vehicle_no, route, vehicle_type, amount, status))
    conn.commit()
    conn.close()

def get_all_records():
    """සියලුම දත්ත Pandas DataFrame එකක් ලෙස ලබා ගැනීම"""
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT * FROM bills ORDER BY id DESC", conn)
    conn.close()
    return df

def update_db_from_dataframe(df):
    """Web App එකේ table එකෙන් edit කරන දත්ත නැවත සේව් කිරීම"""
    conn = sqlite3.connect(DB_NAME)
    df.to_sql("bills", conn, if_exists="replace", index=False)
    conn.close()