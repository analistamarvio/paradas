import json, os, tempfile
from threading import Lock
from typing import Any, Dict, List
from json import JSONDecodeError

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DATA_DIR = os.path.join(BASE_DIR, 'data')
_lock = Lock()

FILES = {
    'status': os.path.join(DATA_DIR, 'status_tear.json'),
    'motivos': os.path.join(DATA_DIR, 'motivos.json'),
    'turnos': os.path.join(DATA_DIR, 'turnos.json'),
    'teares': os.path.join(DATA_DIR, 'teares.json'),  # <- NOVO
    'users': os.path.join(DATA_DIR, 'users.json'),
    'sessions': os.path.join(DATA_DIR, 'sessions.json'),

}

_DEF_STATUS: List[Dict[str, Any]] = []
_DEF_MOTIVOS = [
    {"codigo": 103, "descricao": "Sem operador"},
    {"codigo": 204, "descricao": "Falta programação"},
]
# 3 turnos/dia para 1..7
_DEF_TURNOS: List[Dict[str, Any]] = []
for dow in range(1, 8):
    _DEF_TURNOS += [
        {"turno": 1, "dia_semana": dow, "inicio": "05:00", "fim": "14:00"},
        {"turno": 2, "dia_semana": dow, "inicio": "14:00", "fim": "22:00"},
        {"turno": 3, "dia_semana": dow, "inicio": "22:00", "fim": "05:00"},
    ]

_DEF_TEARES: List[Dict[str, Any]] = []  # <- NOVO

_DEF_USERS = []          # lista de dicts {cod, nome, senha_hash, role}
_DEF_SESSIONS = []       # [{token, cod, created_at}]
_DEFAULTS = {
    'status': _DEF_STATUS,
    'motivos': _DEF_MOTIVOS,
    'turnos': _DEF_TURNOS,
    'teares': _DEF_TEARES,  # <- NOVO
    'users': _DEF_USERS,
    'sessions': _DEF_SESSIONS,
}

def _ensure_file(path: str, default):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(default, f, ensure_ascii=False, indent=2)

for key, default in _DEFAULTS.items():
    _ensure_file(FILES[key], default)

def _safe_load(path: str, default):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (JSONDecodeError, OSError, ValueError):
        # arquivo corrompido → recria com default
        _atomic_write(path, default)
        return default

def read(key: str):
    path = FILES[key]
    with _lock:
        return _safe_load(path, _DEFAULTS[key])

def write(key: str, data):
    path = FILES[key]
    with _lock:
        _atomic_write(path, data)

def _atomic_write(path: str, data):
    """Grava JSON em arquivo temporário e troca por os.replace (atômico)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix='.tmp_', suffix='.json')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)  # troca atômica
    except Exception:
        # se der erro, garante remoção do temp
        try: os.remove(tmp)
        except Exception: pass
        raise
