PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS admin_user (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    password_algo TEXT NOT NULL DEFAULT 'scrypt',
    must_change_password INTEGER NOT NULL DEFAULT 0,
    last_login_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS admin_session (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES admin_user(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    csrf_token TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    ip TEXT,
    user_agent TEXT,
    revoked INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_admin_session_expires ON admin_session(expires_at);

CREATE TABLE IF NOT EXISTS platform_template (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    host_patterns TEXT NOT NULL,
    url_template TEXT,
    id_pattern TEXT,
    example TEXT,
    quick_add_mode TEXT NOT NULL DEFAULT 'full_url',
    quality_options TEXT,
    needs_cookie INTEGER NOT NULL DEFAULT 0,
    proxy_recommended INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1,
    source TEXT NOT NULL DEFAULT 'seed',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS room (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sort_order INTEGER NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    custom_name TEXT,
    url TEXT NOT NULL UNIQUE,
    platform_code TEXT NOT NULL REFERENCES platform_template(code),
    quality TEXT NOT NULL DEFAULT '原画',
    note TEXT,
    last_anchor_name TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_room_sort ON room(sort_order);
CREATE INDEX IF NOT EXISTS idx_room_enabled ON room(enabled);

CREATE TABLE IF NOT EXISTS setting_meta (
    section TEXT NOT NULL,
    "key" TEXT NOT NULL,
    label TEXT NOT NULL,
    description TEXT,
    value_type TEXT NOT NULL,
    group_code TEXT NOT NULL,
    options_json TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_secret INTEGER NOT NULL DEFAULT 0,
    is_advanced INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'upstream',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (section, "key")
);

CREATE TABLE IF NOT EXISTS setting_value (
    section TEXT NOT NULL,
    "key" TEXT NOT NULL,
    value TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL,
    updated_by TEXT NOT NULL DEFAULT 'import',
    PRIMARY KEY (section, "key")
);

CREATE TABLE IF NOT EXISTS recording_session (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id INTEGER REFERENCES room(id) ON DELETE SET NULL,
    anchor_name TEXT NOT NULL,
    title TEXT,
    platform_code TEXT NOT NULL,
    quality TEXT NOT NULL,
    file_path TEXT,
    save_dir TEXT,
    status TEXT NOT NULL,
    stop_reason TEXT,
    ffmpeg_pid INTEGER,
    bytes_written INTEGER NOT NULL DEFAULT 0,
    exit_code INTEGER,
    start_at TEXT NOT NULL,
    end_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_session_room ON recording_session(room_id);
CREATE INDEX IF NOT EXISTS idx_session_status ON recording_session(status);

CREATE TABLE IF NOT EXISTS media_file (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    anchor_key TEXT NOT NULL,
    anchor_name TEXT NOT NULL,
    platform_code TEXT,
    path TEXT NOT NULL UNIQUE,
    filename TEXT NOT NULL,
    extension TEXT NOT NULL,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    mtime TEXT NOT NULL,
    duration_seconds REAL,
    playable INTEGER NOT NULL DEFAULT 0,
    session_id INTEGER REFERENCES recording_session(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_media_anchor ON media_file(anchor_key);
CREATE INDEX IF NOT EXISTS idx_media_mtime ON media_file(mtime);
CREATE INDEX IF NOT EXISTS idx_media_ext ON media_file(extension);

CREATE TABLE IF NOT EXISTS conversion_job (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    src_path TEXT NOT NULL UNIQUE,
    dst_path TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    progress REAL NOT NULL DEFAULT 0,
    attempts INTEGER NOT NULL DEFAULT 0,
    error_code TEXT,
    error_message TEXT,
    trigger TEXT NOT NULL DEFAULT 'manual',
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_conversion_status ON conversion_job(status);

CREATE TABLE IF NOT EXISTS live_state (
    room_id INTEGER PRIMARY KEY REFERENCES room(id) ON DELETE CASCADE,
    state TEXT NOT NULL DEFAULT 'disabled',
    anchor_name TEXT,
    title TEXT,
    platform_code TEXT,
    quality TEXT,
    session_id INTEGER,
    file_path TEXT,
    bytes_written INTEGER NOT NULL DEFAULT 0,
    error_code TEXT,
    error_message TEXT,
    started_at TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS control_command (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id TEXT NOT NULL UNIQUE,
    command TEXT NOT NULL,
    payload_json TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    claimed_at TEXT,
    finished_at TEXT,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_command_status ON control_command(status, created_at);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    target_type TEXT,
    target_id TEXT,
    detail_json TEXT,
    ip TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at);

CREATE TABLE IF NOT EXISTS app_meta (
    "key" TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS room_schedule (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id INTEGER NOT NULL REFERENCES room(id) ON DELETE CASCADE,
    weekdays TEXT NOT NULL,
    start_minute INTEGER NOT NULL,
    end_minute INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_schedule_room ON room_schedule(room_id);

CREATE TABLE IF NOT EXISTS notification_template (
    event_code TEXT PRIMARY KEY,
    enabled INTEGER NOT NULL DEFAULT 0,
    title_template TEXT NOT NULL,
    content_template TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notification_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_code TEXT NOT NULL,
    room_id INTEGER,
    channel TEXT NOT NULL,
    status TEXT NOT NULL,
    error TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_notify_dedup
    ON notification_log(event_code, room_id, created_at);
