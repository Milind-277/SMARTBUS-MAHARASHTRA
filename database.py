# database.py - SmartBus Maharashtra - Database connection helper
import os
import mysql.connector
from mysql.connector import Error


def get_db_config():
    """Build a database config from environment variables with safe local defaults."""
    try:
        port = int(os.getenv("MYSQL_PORT", "3306"))
    except ValueError:
        port = 3306

    config = {
        "host": os.getenv("MYSQL_HOST", "localhost"),
        "port": port,
        "user": os.getenv("MYSQL_USER", "root"),
        "password": os.getenv("MYSQL_PASSWORD", ""),
        "database": os.getenv("MYSQL_DATABASE", "smartbus_mh"),
    }

    ssl_disabled = os.getenv("MYSQL_SSL_DISABLED", "false").strip().lower()
    if ssl_disabled not in {"1", "true", "yes", "on"}:
        config["ssl_disabled"] = False
        ssl_ca = os.getenv("MYSQL_SSL_CA")
        if ssl_ca:
            config["ssl_ca"] = ssl_ca
        config["ssl_verify_cert"] = True
        config["ssl_verify_identity"] = True
    return config


DB_CONFIG = get_db_config()


def get_db_connection():
    """Opens and returns a MySQL connection, or None on error."""
    try:
        return mysql.connector.connect(**get_db_config())
    except Error as e:
        print(f"[DB ERROR] {e}")
        return None
