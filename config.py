import os
from dotenv import load_dotenv
from os.path import join, dirname
from typing import Optional
import json
from logger import logger

dotenv_path = join(dirname(__file__), '.env')
load_dotenv(dotenv_path)

### OPENROUTER
OPENROUTER_CONFIG = {
    "url": os.getenv("OPENROUTER_API_URL"),
    "key": os.getenv("OPENROUTER_API_KEY"),
    "model": os.getenv("OPENROUTER_MODEL_ID")
}

# Chat / thread base
API_TOKEN: str = os.getenv("API_TOKEN", "")
if not API_TOKEN:
    raise ValueError("Falta API_TOKEN en el entorno")

CHAT_ID_STR = os.getenv("CHAT_ID", "")
CHAT_ID: Optional[int] = int(CHAT_ID_STR) if CHAT_ID_STR else None

ADHOC_CHAT_ID_STR = os.getenv("ADHOC_CHAT_ID", "")
ADHOC_CHAT_ID: Optional[int] = int(ADHOC_CHAT_ID_STR) if ADHOC_CHAT_ID_STR else None

# Modo y destinos
IS_PROD = os.getenv("IS_PROD", "false").lower() == "true"
DEV_CHAT_ID = int(os.getenv("DEV_CHAT_ID"))

UID_GRUPO_ID_STR = os.getenv("UID_GRUPO_ID", "")
if UID_GRUPO_ID_STR:
    UID_GRUPO_ID = [int(x.strip()) for x in UID_GRUPO_ID_STR.split(",") if x.strip()]
else:
    UID_GRUPO_ID = []

TARGET_CONTEXTS_STR = os.getenv("TARGET_CONTEXTS", "")
TARGET_CONTEXTS: list[tuple[int, int | None]] = []
if TARGET_CONTEXTS_STR:
    for part in TARGET_CONTEXTS_STR.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            cid_str, tid_str = part.split(":", 1)
            chat_id = int(cid_str)
            thread_id = None if tid_str.lower() == "none" else int(tid_str)
        else:
            chat_id = int(part)
            thread_id = None
        TARGET_CONTEXTS.append((chat_id, thread_id))


def get_target_contexts() -> list[tuple[int, int | None]]:
    if IS_PROD and TARGET_CONTEXTS:
        return TARGET_CONTEXTS
    else:
        return [(DEV_CHAT_ID, None)]
