from __future__ import annotations
# logger.py
import logging

# 1) Silenciar APScheduler de verdad
for name in (
    "apscheduler",
    "apscheduler.scheduler",
    "apscheduler.executors",
    "apscheduler.executors.default",
    "apscheduler.jobstores",
    "apscheduler.jobstores.default",
):
    lg = logging.getLogger(name)
    lg.handlers.clear()          # opcional: por si PTB/apscheduler añade alguno
    lg.propagate = False
    lg.disabled = True           # esto lo apaga

# 2) Tu logger normal
logger = logging.getLogger("bot_logger")
logger.setLevel(logging.INFO)

if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(ch)
    logger.propagate = False     # evita duplicados si hay root handler
