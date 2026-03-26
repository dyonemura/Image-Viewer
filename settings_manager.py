import json
import os

SETTINGS_FILE = "settings.json"

DEFAULT_SETTINGS = {
    "confirm_deletes": True,
    "fast_delete": False
}

def load_settings():
    if not os.path.exists(SETTINGS_FILE):
        save_settings_json(DEFAULT_SETTINGS)
        return DEFAULT_SETTINGS.copy()
    with open(SETTINGS_FILE) as f:
        return {**DEFAULT_SETTINGS, **json.load(f)}

def save_settings_json(settings):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=4)