"""
main.py — Entry point for the HLS Proxy server.

Configures logging (console + file) and starts the Flask dev server.
Log file: logs/proxy.log (auto-created, rotated at 5 MB, keeps 3 backups).

Usage:
    python main.py
"""

import os
import logging
from logging.handlers import RotatingFileHandler
from config import HOST, PORT, STREAM_URL, REFERER

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOG_DIR, "proxy.log")
LOG_FORMAT = "%(asctime)s [%(levelname)-5s] %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

def setup_logging():
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT))
    root.addHandler(console)
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT))
    root.addHandler(file_handler)

    logging.getLogger("werkzeug").setLevel(logging.WARNING)

if __name__ == "__main__":
    setup_logging()

    logger = logging.getLogger("hls_proxy")
    logger.info("=" * 60)
    logger.info("HLS Proxy starting")
    logger.info(f"  Server   : http://{HOST}:{PORT}")
    logger.info(f"  Playlist : http://{HOST}:{PORT}/playlist")
    logger.info(f"  Stream   : {STREAM_URL}")
    logger.info(f"  Referer  : {REFERER}")
    logger.info(f"  Log file : {LOG_FILE}")
    logger.info("=" * 60)

    from app import app
    app.run(host=HOST, port=PORT, debug=False, threaded=True)
