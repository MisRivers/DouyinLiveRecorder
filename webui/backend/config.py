import os
import secrets
import shutil
import sys
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))
if FROZEN:
    ROOT_DIR = Path(sys.executable).resolve().parent
    BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", ROOT_DIR))
else:
    ROOT_DIR = Path(__file__).resolve().parents[2]
    BUNDLE_DIR = ROOT_DIR

BACKEND_DIR = Path(__file__).resolve().parent
FRONTEND_DIST = BUNDLE_DIR / "webui" / "backend" / "static"

DATA_DIR = Path(os.environ.get("DLR_DATA_DIR", ROOT_DIR / "data")).resolve()
CONFIG_DIR = Path(os.environ.get("DLR_CONFIG_DIR", ROOT_DIR / "config")).resolve()
DOWNLOAD_DIR = Path(os.environ.get("DLR_DOWNLOAD_DIR", ROOT_DIR / "downloads")).resolve()
LOG_DIR = Path(os.environ.get("DLR_LOG_DIR", ROOT_DIR / "logs")).resolve()
BACKUP_DIR = DATA_DIR / "backups"
THUMB_DIR = DATA_DIR / "thumbs"
DB_PATH = DATA_DIR / "app.db"
SECRET_PATH = DATA_DIR / "secret.key"

PORT = int(os.environ.get("DLR_PORT", "8642"))
HOST = os.environ.get("DLR_HOST", "0.0.0.0")
SESSION_COOKIE = "dlr_session"
CSRF_HEADER = "X-CSRF-Token"
SESSION_HOURS = 24
LOGIN_MAX_FAILURES = 5
LOGIN_LOCK_SECONDS = 900
TRUST_PROXY = os.environ.get("DLR_TRUST_PROXY", "").lower() in ("1", "true", "yes", "on")


def ensure_dirs() -> None:
    for path in (DATA_DIR, CONFIG_DIR, DOWNLOAD_DIR, LOG_DIR, BACKUP_DIR, THUMB_DIR):
        path.mkdir(parents=True, exist_ok=True)
    _seed_config_files()


def _seed_config_files() -> None:
    bundled = BUNDLE_DIR / "config"
    if bundled.resolve() == CONFIG_DIR.resolve() or not bundled.exists():
        return
    for name in ("config.ini", "URL_config.ini"):
        source = bundled / name
        target = CONFIG_DIR / name
        if source.exists() and not target.exists():
            try:
                shutil.copy2(source, target)
            except OSError:
                pass


def load_secret_key() -> bytes:
    ensure_dirs()
    env = os.environ.get("DLR_SECRET_KEY")
    if env:
        return env.encode("utf-8")
    if SECRET_PATH.exists():
        return SECRET_PATH.read_bytes()
    key = secrets.token_bytes(48)
    SECRET_PATH.write_bytes(key)
    try:
        SECRET_PATH.chmod(0o600)
    except OSError:
        pass
    return key


def save_path_from_settings(settings: dict) -> Path:
    raw = (settings.get("直播保存路径(不填则默认)") or "").strip()
    if not raw:
        return DOWNLOAD_DIR
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (ROOT_DIR / path).resolve()
    return path
