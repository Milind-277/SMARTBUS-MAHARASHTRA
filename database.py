# database.py - SmartBus Maharashtra - Database connection helper
import os
import tempfile

import mysql.connector
from mysql.connector import Error


def _write_ca_to_temp_file(cert_text):
    """Write an Aiven or custom CA bundle to a temp file and return the path."""
    if not cert_text:
        return None
    with tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False) as handle:
        handle.write(cert_text)
        return handle.name


def get_db_config():
    """Build a database config from environment variables with secure defaults."""
    try:
        port = int(os.getenv("MYSQL_PORT", "3306"))
    except ValueError:
        port = 3306

    host = os.getenv("MYSQL_HOST", "localhost")
    config = {
        "host": host,
        "port": port,
        "user": os.getenv("MYSQL_USER", "root"),
        "password": os.getenv("MYSQL_PASSWORD", ""),
        "database": os.getenv("MYSQL_DATABASE", "smartbus_mh"),
    }

    ssl_disabled_value = os.getenv("MYSQL_SSL_DISABLED")
    if ssl_disabled_value is None:
        ssl_disabled_value = "true" if host.lower() in {"localhost", "127.0.0.1"} else "false"
    ssl_disabled = ssl_disabled_value.strip().lower()

    if ssl_disabled in {"1", "true", "yes", "on"}:
        config["ssl_disabled"] = True
        return config

    config["ssl_disabled"] = False
    config["ssl_verify_cert"] = os.getenv("MYSQL_SSL_VERIFY_CERT", "true").strip().lower() not in {"0", "false", "no", "off"}
    config["ssl_verify_identity"] = config["ssl_verify_cert"]

    cert_content = os.getenv("AIVEN_CA_CERT") or os.getenv("MYSQL_SSL_CA")
    if cert_content:
        config["ssl_ca"] = _write_ca_to_temp_file(cert_content)
    elif os.getenv("MYSQL_SSL_CA_PATH"):
        config["ssl_ca"] = os.getenv("MYSQL_SSL_CA_PATH")

    return config


DB_CONFIG = get_db_config()


def get_db_connection():
    """Opens and returns a MySQL connection, or None on error."""
    try:
        return mysql.connector.connect(**get_db_config())
    except Error as e:
        print(f"[DB ERROR] {e}")
        return None
