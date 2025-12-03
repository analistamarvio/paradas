-- Schema for controle de paradas
CREATE TABLE IF NOT EXISTS sectors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    level INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS shift_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS shifts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    shift_type_id INTEGER,
    day INTEGER NOT NULL,
    start_1 TEXT NOT NULL,
    end_1 TEXT NOT NULL,
    total_minutes INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (shift_type_id) REFERENCES shift_types(id)
);

CREATE TABLE IF NOT EXISTS looms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    number TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    shift_id INTEGER,
    sector_id INTEGER,
    FOREIGN KEY (shift_id) REFERENCES shifts(id),
    FOREIGN KEY (sector_id) REFERENCES sectors(id)
);

CREATE TABLE IF NOT EXISTS user_shift_types (
    user_id INTEGER NOT NULL,
    shift_type_id INTEGER NOT NULL,
    PRIMARY KEY (user_id, shift_type_id),
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (shift_type_id) REFERENCES shift_types(id)
);

CREATE TABLE IF NOT EXISTS reasons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code INTEGER NOT NULL UNIQUE,
    description TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS status_tear (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    loom_id INTEGER NOT NULL,
    reason_id INTEGER,
    status INTEGER NOT NULL, -- 0=parado, 1=ligado
    stop_time TEXT,
    start_time TEXT,
    user_id INTEGER,
    user_name TEXT,
    FOREIGN KEY (loom_id) REFERENCES looms(id),
    FOREIGN KEY (reason_id) REFERENCES reasons(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);
