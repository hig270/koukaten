# init_db.py
# データベースとテーブルを初期化するスクリプト
# Windows / RaspberryPi 共通で動作します

import mysql.connector
import os
from dotenv import load_dotenv

# .env読み込み
load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME"),
}

# 各テーブルの作成SQL
TABLES = {}

TABLES["members"] = """
CREATE TABLE IF NOT EXISTS members (
  userId INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(100),
  studentNumber VARCHAR(10),
  inside BOOLEAN DEFAULT FALSE,
  embedding JSON,
  faceScore FLOAT,
  faceImage LONGBLOB,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
"""

TABLES["inside_persons"] = """
CREATE TABLE IF NOT EXISTS inside_persons (
  id INT AUTO_INCREMENT PRIMARY KEY,
  userId INT NOT NULL,
  name VARCHAR(100),
  studentNumber VARCHAR(10),
  faceImage LONGBLOB,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
"""

TABLES["log"] = """
CREATE TABLE IF NOT EXISTS log (
  id INT AUTO_INCREMENT PRIMARY KEY,
  idempotencyKey VARCHAR(64) UNIQUE,
  userId INT,
  name VARCHAR(100),
  studentNumber VARCHAR(10),
  timestamp DATETIME,
  state ENUM('入室','退室'),
  raw_json JSON
);
"""

TABLES["userData"] = """
CREATE TABLE IF NOT EXISTS userData (
  id INT AUTO_INCREMENT PRIMARY KEY,
  userId INT,
  name VARCHAR(100),
  studentNumber VARCHAR(10),
  enter_time DATETIME,
  leave_time DATETIME
);
"""

def init_database():
    print("Connecting to MySQL...")
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()

    print("Creating tables...")
    for name, ddl in TABLES.items():
        print(f" - {name}")
        cursor.execute(ddl)

    conn.commit()
    cursor.close()
    conn.close()
    print("Database initialization complete!")

if __name__ == "__main__":
    init_database()
