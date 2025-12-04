# -*- coding: utf-8 -*-
import os
import sqlite3
import sys
from functools import wraps
from typing import Optional
import datetime
from zoneinfo import ZoneInfo

from flask import Flask, g, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash

DATABASE = os.path.join(os.path.dirname(__file__), 'paradas.db')
API_DATABASE = os.path.join(os.path.dirname(__file__), 'api.db')
SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-me')
DAY_LABELS = ['Domingo', 'Segunda-feira', 'Ter\u00e7a-feira', 'Quarta-feira', 'Quinta-feira', 'Sexta-feira', 'S\u00e1bado']
REASONS_SEED = [
    (9, 'MANUTEN\u00c7\u00c3O'),
    (8, 'FALTA PROGRAMA\u00c7\u00c3O'),
    (16, 'MATERIA PRIMA'),
    (10, 'FALTA OPERADOR'),
    (19, 'FALTA DE ENERGIA / AR'),
    (100, 'HOR\u00c1RIO DO LANCHE/ALMO\u00c7O/JANTA'),
    (3, 'PROBLEMA EL\u00c9TRICO'),
    (5, 'TROCA DE ARTIGO'),
    (7, 'FALTA FIO'),
    (11, 'AJUSTE DE M\u00c1QUINA'),
    (12, 'LIMPEZA'),
    (13, 'REUNI\u00c3O'),
    (14, 'TESTE QUALIDADE'),
    (17, 'CORTE DE MALHA'),
    (20, 'TROCA DE LYCRA'),
    (24, 'SALDO DE FIOS'),
    (26, 'AGUARDANDO MEC\u00c2NICO'),
    (27, 'AMOSTRA DE MALHA'),
]

app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY

def user_level() -> int:
    try:
        return int(session.get('level', 0))
    except Exception:
        return 0

def level_required(allowed_levels):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if user_level() not in allowed_levels:
                flash('Acesso negado.', 'danger')
                return redirect(url_for('dashboard'))
            return func(*args, **kwargs)
        return wrapper
    return decorator


def parse_time_to_minutes(value: str) -> int:
    if not value:
        raise ValueError('Horário obrigatório')
    parts = value.split(':')
    if len(parts) != 2:
        raise ValueError('Formato inválido, use HH:MM')
    hour, minute = parts
    hour_i = int(hour)
    minute_i = int(minute)
    if hour_i < 0 or hour_i > 23 or minute_i < 0 or minute_i > 59:
        raise ValueError('Horário fora do intervalo')
    return hour_i * 60 + minute_i


def delta_minutes(start: str, end: str) -> int:
    start_m = parse_time_to_minutes(start)
    end_m = parse_time_to_minutes(end)
    return (end_m - start_m) % (24 * 60)


def compute_total_minutes(start_1: str, end_1: str) -> int:
    return delta_minutes(start_1, end_1)


def format_total(total_minutes: Optional[int]) -> str:
    if total_minutes is None:
        return '-'
    hours = total_minutes // 60
    minutes = total_minutes % 60
    return f"{hours:02d}:{minutes:02d}"


def day_label(day: Optional[int]) -> str:
    try:
        return DAY_LABELS[int(day)]
    except Exception:
        return '-'


def now_local():
    try:
        tz = ZoneInfo("America/Sao_Paulo")
    except Exception:
        # fallback fixo de -03:00 para evitar divergências em servidores sem tzdata
        tz = datetime.timezone(datetime.timedelta(hours=-3))
    return datetime.datetime.now(tz)


def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        # Garantir tabelas/colunas novas em bancos já existentes.
        g.db.execute(
            'CREATE TABLE IF NOT EXISTS shift_types (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE)'
        )
        g.db.execute(
            '''CREATE TABLE IF NOT EXISTS shifts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                shift_type_id INTEGER,
                day INTEGER NOT NULL DEFAULT 0,
                start_1 TEXT,
                end_1 TEXT,
                total_minutes INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (shift_type_id) REFERENCES shift_types(id)
            )'''
        )
        g.db.execute(
            '''CREATE TABLE IF NOT EXISTS user_shift_types (
                user_id INTEGER NOT NULL,
                shift_type_id INTEGER NOT NULL,
                PRIMARY KEY (user_id, shift_type_id),
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (shift_type_id) REFERENCES shift_types(id)
            )'''
        )
        g.db.execute(
            '''CREATE TABLE IF NOT EXISTS reasons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code INTEGER NOT NULL UNIQUE,
                description TEXT NOT NULL
            )'''
        )
        g.db.execute(
            '''CREATE TABLE IF NOT EXISTS looms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                number TEXT NOT NULL UNIQUE
            )'''
        )
        g.db.execute(
            '''CREATE TABLE IF NOT EXISTS status_tear (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                loom_id INTEGER NOT NULL,
                reason_id INTEGER,
                status INTEGER NOT NULL,
                stop_time TEXT,
                start_time TEXT,
                user_id INTEGER,
                user_name TEXT,
                FOREIGN KEY (loom_id) REFERENCES looms(id),
                FOREIGN KEY (reason_id) REFERENCES reasons(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )'''
        )
        existing_cols = [row['name'] for row in g.db.execute('PRAGMA table_info(shifts)').fetchall()]
        existing_set = set(existing_cols)
        target_cols = ['id', 'shift_type_id', 'day', 'start_1', 'end_1', 'total_minutes']
        if set(target_cols) != existing_set:
            # Migração simples para remover colunas não utilizadas.
            g.db.execute(
                '''CREATE TABLE IF NOT EXISTS shifts_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    shift_type_id INTEGER,
                    day INTEGER NOT NULL DEFAULT 0,
                    start_1 TEXT,
                    end_1 TEXT,
                    total_minutes INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (shift_type_id) REFERENCES shift_types(id)
                )'''
            )
            g.db.execute(
                '''INSERT INTO shifts_new (id, shift_type_id, day, start_1, end_1, total_minutes)
                   SELECT id, shift_type_id, COALESCE(day, 0), start_1, end_1, COALESCE(total_minutes, 0)
                   FROM shifts'''
            )
            g.db.execute('DROP TABLE shifts')
            g.db.execute('ALTER TABLE shifts_new RENAME TO shifts')
            for row in g.db.execute('SELECT id, start_1, end_1 FROM shifts').fetchall():
                try:
                    total = compute_total_minutes(row['start_1'], row['end_1'])
                    g.db.execute('UPDATE shifts SET total_minutes = ? WHERE id = ?', (total, row['id']))
                except Exception:
                    continue
            g.db.commit()
        # re-leitura para capturar colunas atuais
        g.shift_cols = {row['name'] for row in g.db.execute('PRAGMA table_info(shifts)').fetchall()}

        looms_cols = {row['name'] for row in g.db.execute('PRAGMA table_info(looms)').fetchall()}
        target_looms = {'id', 'name', 'number'}
        if not looms_cols:
            g.db.execute(
                '''CREATE TABLE IF NOT EXISTS looms (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    number TEXT NOT NULL UNIQUE
                )'''
            )
        elif looms_cols != target_looms:
            g.db.execute(
                '''CREATE TABLE IF NOT EXISTS looms_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    number TEXT NOT NULL UNIQUE
                )'''
            )
            g.db.execute('INSERT INTO looms_new (id, name, number) SELECT id, name, number FROM looms')
            g.db.execute('DROP TABLE looms')
            g.db.execute('ALTER TABLE looms_new RENAME TO looms')

        ensure_reasons_seed(g.db)
    return g.db


def get_api_db():
    """Conexão separada para api.db (tabela api)."""
    if 'api_db' not in g:
        g.api_db = sqlite3.connect(API_DATABASE)
        g.api_db.row_factory = sqlite3.Row
        g.api_db.execute(
            '''CREATE TABLE IF NOT EXISTS api (
                id_api INTEGER PRIMARY KEY AUTOINCREMENT,
                tear INTEGER,
                hora_inicio TEXT,
                hora_fim TEXT,
                data TEXT,
                cod_motivo INTEGER,
                motivo TEXT,
                turno TEXT,
                responsavel TEXT,
                status_id INTEGER
            )'''
        )
        cols = {row['name'] for row in g.api_db.execute('PRAGMA table_info(api)').fetchall()}
        if 'status_id' not in cols:
            g.api_db.execute('ALTER TABLE api ADD COLUMN status_id INTEGER')
        g.api_db.commit()
    return g.api_db


@app.teardown_appcontext
def close_db(error=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()
    api_db = g.pop('api_db', None)
    if api_db is not None:
        api_db.close()


def init_db():
    db = sqlite3.connect(DATABASE)
    with open(os.path.join(os.path.dirname(__file__), 'schema.sql'), 'r', encoding='utf-8') as f:
        db.executescript(f.read())
    ensure_reasons_seed(db)
    db.commit()
    db.close()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if 'user_id' not in session:
            flash('Faça login para continuar.', 'warning')
            return redirect(url_for('login'))
        return view(*args, **kwargs)

    return wrapped


def level_allowed(levels):
    """Helper para verificar se o n?vel atual est? na lista permitida."""
    try:
        return user_level() in levels
    except Exception:
        return False

def parse_iso_naive(value: Optional[str]) -> Optional[datetime.datetime]:
    """Converte string ISO (com ou sem timezone) em datetime naive."""
    if not value:
        return None
    try:
        dt_obj = datetime.datetime.fromisoformat(value)
    except Exception:
        return None
    return dt_obj.replace(tzinfo=None) if dt_obj.tzinfo else dt_obj



@app.context_processor
def inject_helpers():
    return {
        'day_label': day_label,
        'format_total': format_total,
        'user_level': user_level,
        'level_allowed': level_allowed,
    }

def build_heatmap_data(db, looms, shift_types, start_date, end_date, selected_looms, selected_shift_type):
    running_ctx = build_report_data(
        db,
        looms,
        shift_types,
        start_date,
        end_date,
        'working',
        selected_looms,
        selected_shift_type,
    )
    stopped_ctx = build_report_data(
        db,
        looms,
        shift_types,
        start_date,
        end_date,
        'stopped',
        selected_looms,
        selected_shift_type,
    )
    running_map = {}
    for r in running_ctx.get('report', []):
        if r.get('loom'):
            running_map[r['loom']['id']] = r.get('values', [])
    stopped_map = {}
    for r in stopped_ctx.get('report', []):
        if r.get('loom'):
            stopped_map[r['loom']['id']] = r.get('values', [])

    heatmap_data = []
    for r in stopped_ctx.get('report', []):
        loom_row = r.get('loom')
        if not loom_row:
            continue
        loom_id = loom_row['id']
        loom_number = loom_row['number']
        heatmap_data.append(
            {
                'loom_number': loom_number,
                'values': r.get('values', []),
                'running_values': running_map.get(loom_id, []),
                'stopped_values': stopped_map.get(loom_id, []),
            }
        )
    return heatmap_data, stopped_ctx.get('day_labels', [])


def ensure_reasons_seed(db: sqlite3.Connection) -> None:
    existing_codes = {row['code'] for row in db.execute('SELECT code FROM reasons').fetchall()}
    missing = [(code, desc) for code, desc in REASONS_SEED if code not in existing_codes]
    if missing:
        db.executemany('INSERT OR IGNORE INTO reasons (code, description) VALUES (?, ?)', missing)
        db.commit()


def build_dashboard_teares_context():
    db = get_db()
    current_weekday = now_local().weekday()
    looms = db.execute('SELECT id, number FROM looms ORDER BY number').fetchall()
    statuses = {
        row['loom_id']: row
        for row in db.execute(
            '''SELECT st.* , r.description AS reason_desc
               FROM status_tear st
               LEFT JOIN reasons r ON r.id = st.reason_id
               WHERE st.id IN (
                 SELECT MAX(id) FROM status_tear GROUP BY loom_id
               )'''
        ).fetchall()
    }
    now = now_local()
    now_naive = now.replace(tzinfo=None)
    cards = []
    for loom in looms:
        st = statuses.get(loom['id'])
        status = st['status'] if st else 1
        ref_str = None
        if st:
            ref_str = st['stop_time'] if status == 0 else st['start_time']
        ref_dt = datetime.datetime.fromisoformat(ref_str) if ref_str else None
        if ref_dt:
            if ref_dt.tzinfo is None:
                if ref_dt > now_naive:
                    ref_dt = now_naive
                delta = now_naive - ref_dt
            else:
                if ref_dt > now:
                    ref_dt = now
                delta = now - ref_dt
            since_minutes = int(delta.total_seconds() // 60)
        else:
            since_minutes = None
        cards.append(
            {
                'id': loom['id'],
                'number': loom['number'],
                'status': status,
                'since_text': f"{since_minutes//60:02d}:{since_minutes%60:02d} horas" if since_minutes is not None else '-',
                'since_label': 'Parado há' if status == 0 else 'Funcionando há',
                'reason': st['reason_desc'] if st else None,
                'stop_time': st['stop_time'] if st else None,
                'start_time': st['start_time'] if st else None,
                'reason_id': st['reason_id'] if st else None,
            }
        )

    reasons = db.execute('SELECT id, code, description FROM reasons ORDER BY code').fetchall()
    user_shifts = get_user_shifts_today(session['user_id'], db, current_weekday) if 'user_id' in session else []
    return {'cards': cards, 'reasons': reasons, 'user_shifts': user_shifts, 'now': now, 'current_weekday': current_weekday}


def get_user_shifts_today(user_id: int, db: sqlite3.Connection, weekday: Optional[int] = None):
    weekday = weekday if weekday is not None else now_local().weekday()
    return db.execute(
        '''SELECT sh.*, st.name AS type_name
           FROM shifts sh
           JOIN user_shift_types ust ON ust.shift_type_id = sh.shift_type_id
           JOIN shift_types st ON st.id = sh.shift_type_id
           WHERE ust.user_id = ? AND sh.day = ?
           ORDER BY sh.start_1''',
        (user_id, weekday),
    ).fetchall()


def get_shift_label(shift_id: Optional[int], db: sqlite3.Connection) -> Optional[str]:
    if not shift_id:
        return None
    row = db.execute(
        '''SELECT sh.*, st.name AS type_name
           FROM shifts sh
           LEFT JOIN shift_types st ON st.id = sh.shift_type_id
           WHERE sh.id = ?''',
        (shift_id,),
    ).fetchone()
    if not row:
        return None
    return f"{row['type_name'] or '-'} ({row['start_1']} - {row['end_1']})"


def time_in_shift(time_str: str, shift_row) -> bool:
    """Valida se o horário HH:MM está dentro da janela do turno."""
    try:
        minutes = parse_time_to_minutes(time_str)
    except Exception:
        return False
    start1 = parse_time_to_minutes(shift_row['start_1'])
    end1 = parse_time_to_minutes(shift_row['end_1'])

    def in_window(start_m, end_m):
        if start_m <= end_m:
            return start_m <= minutes <= end_m
        # vira o dia
        return minutes >= start_m or minutes <= end_m

    if in_window(start1, end1):
        return True
    return False


@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        db = get_db()
        user = db.execute(
            '''SELECT u.*, s.level AS sector_level
               FROM users u
               LEFT JOIN sectors s ON s.id = u.sector_id
               WHERE u.username = ?''',
            (username,),
        ).fetchone()
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['level'] = user['sector_level'] if user['sector_level'] is not None else 0
            flash('Login realizado.', 'success')
            return redirect(url_for('dashboard'))
        flash('Usuário ou senha inválidos.', 'danger')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Sessão encerrada.', 'info')
    return redirect(url_for('login'))


@app.route('/dashboard')
@login_required
def dashboard():
    db = get_db()
    counts = {
        'users': db.execute('SELECT COUNT(*) FROM users').fetchone()[0],
        'sectors': db.execute('SELECT COUNT(*) FROM sectors').fetchone()[0],
        'shifts': db.execute('SELECT COUNT(*) FROM shifts').fetchone()[0],
        'looms': db.execute('SELECT COUNT(*) FROM looms').fetchone()[0],
        'shift_types': db.execute('SELECT COUNT(*) FROM shift_types').fetchone()[0],
        'reasons': db.execute('SELECT COUNT(*) FROM reasons').fetchone()[0],
    }
    return render_template('dashboard.html', counts=counts)


# --- Users ---
@app.route('/users')
@login_required
@level_required([6])
def users_list():
    db = get_db()
    users = db.execute('''
        SELECT
            u.id,
            u.username,
            s.name AS sector_name,
            GROUP_CONCAT(st.name, ' / ') AS shift_types
        FROM users u
        LEFT JOIN sectors s ON s.id = u.sector_id
        LEFT JOIN user_shift_types ust ON ust.user_id = u.id
        LEFT JOIN shift_types st ON st.id = ust.shift_type_id
        GROUP BY u.id, u.username, s.name
        ORDER BY u.username
    ''').fetchall()
    return render_template('users.html', users=users)


@app.route('/users/new', methods=['GET', 'POST'])
@login_required
@level_required([6])
def users_create():
    db = get_db()
    sectors = db.execute('SELECT id, name FROM sectors ORDER BY name').fetchall()
    shift_types = db.execute('SELECT id, name FROM shift_types ORDER BY name').fetchall()
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        sector_id = request.form.get('sector_id') or None
        shift_type_ids = [int(x) for x in request.form.getlist('shift_type_ids') if x]
        if not username or not password:
            flash('Usuário e senha são obrigatórios.', 'danger')
        else:
            try:
                primary_shift_id = shift_type_ids[0] if shift_type_ids else None
                cur = db.execute(
                    'INSERT INTO users (username, password_hash, sector_id, shift_id) VALUES (?, ?, ?, ?)',
                    (username, generate_password_hash(password), sector_id, primary_shift_id),
                )
                user_id = cur.lastrowid
                if shift_type_ids:
                    db.executemany(
                        'INSERT OR IGNORE INTO user_shift_types (user_id, shift_type_id) VALUES (?, ?)',
                        [(user_id, sid) for sid in shift_type_ids],
                    )
                db.commit()
                flash('Usuário criado.', 'success')
                return redirect(url_for('users_list'))
            except sqlite3.IntegrityError:
                flash('Nome de usuário já existe.', 'danger')
    return render_template('user_form.html', sectors=sectors, shift_types=shift_types, selected_shift_types=[], action_url=url_for('users_create'), user=None)


@app.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@level_required([6])
def users_edit(user_id):
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    if not user:
        flash('Usuário não encontrado.', 'danger')
        return redirect(url_for('users_list'))

    sectors = db.execute('SELECT id, name FROM sectors ORDER BY name').fetchall()
    shift_types = db.execute('SELECT id, name FROM shift_types ORDER BY name').fetchall()
    selected_shift_types = [row['shift_type_id'] for row in db.execute('SELECT shift_type_id FROM user_shift_types WHERE user_id = ?', (user_id,)).fetchall()]

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        sector_id = request.form.get('sector_id') or None
        shift_type_ids = [int(x) for x in request.form.getlist('shift_type_ids') if x]
        if not username:
            flash('Usuário é obrigatório.', 'danger')
        else:
            try:
                primary_shift_id = shift_type_ids[0] if shift_type_ids else None
                if password:
                    password_hash = generate_password_hash(password)
                    db.execute(
                        'UPDATE users SET username = ?, password_hash = ?, sector_id = ?, shift_id = ? WHERE id = ?',
                        (username, password_hash, sector_id, primary_shift_id, user_id),
                    )
                else:
                    db.execute(
                        'UPDATE users SET username = ?, sector_id = ?, shift_id = ? WHERE id = ?',
                        (username, sector_id, primary_shift_id, user_id),
                    )
                db.execute('DELETE FROM user_shift_types WHERE user_id = ?', (user_id,))
                if shift_type_ids:
                    db.executemany(
                        'INSERT OR IGNORE INTO user_shift_types (user_id, shift_type_id) VALUES (?, ?)',
                        [(user_id, sid) for sid in shift_type_ids],
                    )
                db.commit()
                flash('Usuário atualizado.', 'success')
                return redirect(url_for('users_list'))
            except sqlite3.IntegrityError:
                flash('Nome de usuário já existe.', 'danger')
    return render_template('user_form.html', sectors=sectors, shift_types=shift_types, selected_shift_types=selected_shift_types, action_url=url_for('users_edit', user_id=user_id), user=user)


@app.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
@level_required([6])
def users_delete(user_id):
    db = get_db()
    db.execute('DELETE FROM users WHERE id = ?', (user_id,))
    db.commit()
    flash('Usuário removido.', 'info')
    return redirect(url_for('users_list'))


# --- Sectors ---
@app.route('/sectors')
@login_required
@level_required([5, 6])
def sectors_list():
    db = get_db()
    sectors = db.execute('SELECT * FROM sectors ORDER BY name').fetchall()
    return render_template('sectors.html', sectors=sectors)


@app.route('/sectors/new', methods=['GET', 'POST'])
@login_required
@level_required([5, 6])
def sectors_create():
    if request.method == 'POST':
        name = request.form.get('name')
        level = request.form.get('level')
        if not name or not level:
            flash('Nome e nível são obrigatórios.', 'danger')
        else:
            db = get_db()
            try:
                db.execute('INSERT INTO sectors (name, level) VALUES (?, ?)', (name, int(level)))
                db.commit()
                flash('Setor criado.', 'success')
                return redirect(url_for('sectors_list'))
            except sqlite3.IntegrityError:
                flash('Nome do setor já existe.', 'danger')
    return render_template('sector_form.html', action_url=url_for('sectors_create'), sector=None)


@app.route('/sectors/<int:sector_id>/edit', methods=['GET', 'POST'])
@login_required
@level_required([5, 6])
def sectors_edit(sector_id):
    db = get_db()
    sector = db.execute('SELECT * FROM sectors WHERE id = ?', (sector_id,)).fetchone()
    if not sector:
        flash('Setor não encontrado.', 'danger')
        return redirect(url_for('sectors_list'))

    if request.method == 'POST':
        name = request.form.get('name')
        level = request.form.get('level')
        if not name or not level:
            flash('Nome e nível são obrigatórios.', 'danger')
        else:
            try:
                db.execute('UPDATE sectors SET name = ?, level = ? WHERE id = ?', (name, int(level), sector_id))
                db.commit()
                flash('Setor atualizado.', 'success')
                return redirect(url_for('sectors_list'))
            except sqlite3.IntegrityError:
                flash('Nome do setor já existe.', 'danger')
    return render_template('sector_form.html', action_url=url_for('sectors_edit', sector_id=sector_id), sector=sector)


@app.route('/sectors/<int:sector_id>/delete', methods=['POST'])
@login_required
@level_required([5, 6])
def sectors_delete(sector_id):
    db = get_db()
    db.execute('DELETE FROM sectors WHERE id = ?', (sector_id,))
    db.commit()
    flash('Setor removido.', 'info')
    return redirect(url_for('sectors_list'))


# --- Shifts ---
@app.route('/shifts')
@login_required
@level_required([5, 6])
def shifts_list():
    db = get_db()
    shifts = db.execute('''
        SELECT sh.*, st.name AS type_name
        FROM shifts sh
        LEFT JOIN shift_types st ON st.id = sh.shift_type_id
        ORDER BY sh.id
    ''').fetchall()
    return render_template('shifts.html', shifts=shifts)


def validate_shift_form(day, start_1, end_1) -> Optional[str]:
    if day is None or day == '':
        return 'Dia da semana é obrigatório.'
    try:
        day_int = int(day)
        if day_int < 0 or day_int > 6:
            return 'Dia deve estar entre 0 (Domingo) e 6 (Sábado).'
    except ValueError:
        return 'Dia inválido.'

    required_times = [start_1, end_1]
    if any(not t for t in required_times):
        return 'Preencha início e fim.'

    try:
        # valida horários
        parse_time_to_minutes(start_1)
        parse_time_to_minutes(end_1)
    except Exception as exc:  # noqa: BLE001 - queremos mensagem simples ao usuário
        return f'Horário inválido: {exc}'
    return None


@app.route('/shifts/new', methods=['GET', 'POST'])
@login_required
@level_required([5, 6])
def shifts_create():
    db = get_db()
    shift_types = db.execute('SELECT id, name FROM shift_types ORDER BY name').fetchall()
    if request.method == 'POST':
        shift_type_id = request.form.get('shift_type_id') or None
        day = request.form.get('day')
        start_1 = request.form.get('start_1')
        end_1 = request.form.get('end_1')
        error = validate_shift_form(day, start_1, end_1)
        if error:
            flash(error, 'danger')
        else:
            total_minutes = compute_total_minutes(start_1, end_1)
            cols = ['shift_type_id', 'day', 'start_1', 'end_1', 'total_minutes']
            values = [shift_type_id, int(day), start_1, end_1, total_minutes]
            shift_cols = getattr(g, 'shift_cols', set())
            if 'weekday' in shift_cols:
                cols.append('weekday')
                values.append(day_label(day))
            if 'start_time' in shift_cols:
                cols.append('start_time')
                values.append(start_1)
            if 'end_time' in shift_cols:
                cols.append('end_time')
                values.append(end_1)
            placeholders = ','.join(['?'] * len(cols))
            db.execute(f"INSERT INTO shifts ({','.join(cols)}) VALUES ({placeholders})", values)
            db.commit()
            flash('Turno criado.', 'success')
            return redirect(url_for('shifts_list'))
    return render_template(
        'shift_form.html',
        action_url=url_for('shifts_create'),
        shift=None,
        shift_types=shift_types,
    )


@app.route('/shifts/<int:shift_id>/edit', methods=['GET', 'POST'])
@login_required
@level_required([5, 6])
def shifts_edit(shift_id):
    db = get_db()
    shift = db.execute('SELECT * FROM shifts WHERE id = ?', (shift_id,)).fetchone()
    if not shift:
        flash('Turno não encontrado.', 'danger')
        return redirect(url_for('shifts_list'))

    shift_types = db.execute('SELECT id, name FROM shift_types ORDER BY name').fetchall()

    if request.method == 'POST':
        shift_type_id = request.form.get('shift_type_id') or None
        day = request.form.get('day')
        start_1 = request.form.get('start_1')
        end_1 = request.form.get('end_1')
        error = validate_shift_form(day, start_1, end_1)
        if error:
            flash(error, 'danger')
        else:
            total_minutes = compute_total_minutes(start_1, end_1)
            cols = ['shift_type_id', 'day', 'start_1', 'end_1', 'total_minutes']
            values = [shift_type_id, int(day), start_1, end_1, total_minutes]
            shift_cols = getattr(g, 'shift_cols', set())
            if 'weekday' in shift_cols:
                cols.append('weekday')
                values.append(day_label(day))
            if 'start_time' in shift_cols:
                cols.append('start_time')
                values.append(start_1)
            if 'end_time' in shift_cols:
                cols.append('end_time')
                values.append(end_1)
            set_clause = ', '.join([f"{c} = ?" for c in cols])
            db.execute(f"UPDATE shifts SET {set_clause} WHERE id = ?", values + [shift_id])
            db.commit()
            flash('Turno atualizado.', 'success')
            return redirect(url_for('shifts_list'))
    return render_template(
        'shift_form.html',
        action_url=url_for('shifts_edit', shift_id=shift_id),
        shift=shift,
        shift_types=shift_types,
    )


@app.route('/shifts/<int:shift_id>/delete', methods=['POST'])
@login_required
@level_required([5, 6])
def shifts_delete(shift_id):
    db = get_db()
    db.execute('DELETE FROM shifts WHERE id = ?', (shift_id,))
    db.commit()
    flash('Turno removido.', 'info')
    return redirect(url_for('shifts_list'))


# --- Shift Types ---
@app.route('/shift-types')
@login_required
@level_required([5, 6])
def shift_types_list():
    db = get_db()
    shift_types = db.execute('SELECT * FROM shift_types ORDER BY name').fetchall()
    return render_template('shift_types.html', shift_types=shift_types)


@app.route('/shift-types/new', methods=['GET', 'POST'])
@login_required
@level_required([5, 6])
def shift_types_create():
    if request.method == 'POST':
        name = request.form.get('name')
        if not name:
            flash('Nome do tipo é obrigatório.', 'danger')
        else:
            db = get_db()
            try:
                db.execute('INSERT INTO shift_types (name) VALUES (?)', (name,))
                db.commit()
                flash('Tipo de turno criado.', 'success')
                return redirect(url_for('shift_types_list'))
            except sqlite3.IntegrityError:
                flash('Nome do tipo de turno já existe.', 'danger')
    return render_template('shift_type_form.html', action_url=url_for('shift_types_create'), shift_type=None)


@app.route('/shift-types/<int:type_id>/edit', methods=['GET', 'POST'])
@login_required
@level_required([5, 6])
def shift_types_edit(type_id):
    db = get_db()
    shift_type = db.execute('SELECT * FROM shift_types WHERE id = ?', (type_id,)).fetchone()
    if not shift_type:
        flash('Tipo de turno não encontrado.', 'danger')
        return redirect(url_for('shift_types_list'))

    if request.method == 'POST':
        name = request.form.get('name')
        if not name:
            flash('Nome do tipo é obrigatório.', 'danger')
        else:
            try:
                db.execute('UPDATE shift_types SET name = ? WHERE id = ?', (name, type_id))
                db.commit()
                flash('Tipo de turno atualizado.', 'success')
                return redirect(url_for('shift_types_list'))
            except sqlite3.IntegrityError:
                flash('Nome do tipo de turno já existe.', 'danger')
    return render_template('shift_type_form.html', action_url=url_for('shift_types_edit', type_id=type_id), shift_type=shift_type)


@app.route('/shift-types/<int:type_id>/delete', methods=['POST'])
@login_required
@level_required([5, 6])
def shift_types_delete(type_id):
    db = get_db()
    db.execute('DELETE FROM shift_types WHERE id = ?', (type_id,))
    db.commit()
    flash('Tipo de turno removido.', 'info')
    return redirect(url_for('shift_types_list'))


# --- Reasons ---
@app.route('/reasons')
@login_required
@level_required([5, 6])
def reasons_list():
    db = get_db()
    reasons = db.execute('SELECT * FROM reasons ORDER BY code').fetchall()
    return render_template('reasons.html', reasons=reasons)


@app.route('/relatorio-motivos')
@login_required
@level_required([4, 5, 6])
def relatorio_motivos():
    db = get_db()
    looms = db.execute('SELECT id, number FROM looms ORDER BY number').fetchall()
    shift_types = db.execute('SELECT id, name FROM shift_types ORDER BY id').fetchall()
    reasons = db.execute('SELECT id, code, description FROM reasons ORDER BY code').fetchall()

    today = now_local().date()
    default_start = (today - datetime.timedelta(days=7)).isoformat()
    default_end = today.isoformat()
    start_date = request.args.get('start_date', default_start)
    end_date = request.args.get('end_date', default_end)
    selected_loom = request.args.get('loom') or ''
    selected_shift_type = request.args.get('shift_type', '')

    report_ctx = build_reason_report_data(
        db,
        looms,
        shift_types,
        reasons,
        start_date,
        end_date,
        selected_loom,
        selected_shift_type,
    )
    return render_template(
        'relatorio_motivos.html',
        looms=looms,
        shift_types=shift_types,
        reasons=reasons,
        fixed_shift_label=None,
        **report_ctx,
    )

def _relatorio_motivos_turno(fixed_shift_index: int, template_name: str):
    db = get_db()
    looms = db.execute('SELECT id, number FROM looms ORDER BY number').fetchall()
    shift_types = db.execute('SELECT id, name FROM shift_types ORDER BY id').fetchall()
    if fixed_shift_index >= len(shift_types):
        flash('Turno não encontrado.', 'warning')
        return redirect(url_for('dashboard'))
    fixed_shift = shift_types[fixed_shift_index]
    reasons = db.execute('SELECT id, code, description FROM reasons ORDER BY code').fetchall()

    today = now_local().date()
    default_start = (today - datetime.timedelta(days=7)).isoformat()
    default_end = today.isoformat()
    start_date = request.args.get('start_date', default_start)
    end_date = request.args.get('end_date', default_end)
    selected_loom = request.args.get('loom') or ''

    selected_shift_type = str(fixed_shift['id'])

    report_ctx = build_reason_report_data(
        db,
        looms,
        shift_types,
        reasons,
        start_date,
        end_date,
        selected_loom,
        selected_shift_type,
    )
    return render_template(
        template_name,
        looms=looms,
        shift_types=[fixed_shift],
        reasons=reasons,
        fixed_shift_label=fixed_shift['name'],
        **report_ctx,
    )

@app.route('/relatorio-motivos-primeiro-turno')
@login_required
@level_required([1, 5, 6])
def relatorio_motivos_primeiro_turno():
    return _relatorio_motivos_turno(0, 'relatorio_motivos.html')

@app.route('/relatorio-motivos-segundo-turno')
@login_required
@level_required([2, 5, 6])
def relatorio_motivos_segundo_turno():
    return _relatorio_motivos_turno(1, 'relatorio_motivos.html')

@app.route('/relatorio-motivos-terceiro-turno')
@login_required
@level_required([3, 5, 6])
def relatorio_motivos_terceiro_turno():
    return _relatorio_motivos_turno(2, 'relatorio_motivos.html')

@app.route('/relatorio-motivos-geral-dia')
@login_required
@level_required([4, 5, 6])
def relatorio_motivos_geral_dia():
    db = get_db()
    shift_types = db.execute('SELECT id, name FROM shift_types WHERE id <> 4 ORDER BY name').fetchall()
    today = now_local().date()
    default_start = (today - datetime.timedelta(days=7)).isoformat()
    default_end = today.isoformat()
    start_date = request.args.get('start_date', default_start)
    end_date = request.args.get('end_date', default_end)
    selected_shift_type = request.args.get('shift_type') or ''

    data_ctx = build_reason_daily_summary(db, start_date, end_date, selected_shift_type)
    return render_template(
        'relatorio_motivos_dia.html',
        shift_types=shift_types,
        heading='RELATORIO DE PARADAS / MOTIVO GERAL',
        **data_ctx,
    )

def _relatorio_paradas_motivo_turno_dia(offset: int, title: str):
    db = get_db()
    shift_row = db.execute('SELECT id, name FROM shift_types WHERE id <> 4 ORDER BY id LIMIT 1 OFFSET ?', (offset,)).fetchone()
    if not shift_row:
        flash('Turno não encontrado.', 'warning')
        return redirect(url_for('dashboard'))

    today = now_local().date()
    default_start = (today - datetime.timedelta(days=7)).isoformat()
    default_end = today.isoformat()
    start_date = request.args.get('start_date', default_start)
    end_date = request.args.get('end_date', default_end)
    selected_shift_type = str(shift_row['id'])

    data_ctx = build_reason_daily_summary(db, start_date, end_date, selected_shift_type)
    return render_template(
        'relatorio_motivos_dia.html',
        shift_types=[shift_row],
        heading=title,
        **data_ctx,
    )

@app.route('/relatorio-paradas-motivo-primeiro-turno')
@login_required
@level_required([1, 5, 6])
def relatorio_paradas_motivo_primeiro_turno():
    return _relatorio_paradas_motivo_turno_dia(0, 'RELATORIO DE PARADAS / MOTIVO 1º TURNO')

@app.route('/relatorio-paradas-motivo-segundo-turno')
@login_required
@level_required([2, 5, 6])
def relatorio_paradas_motivo_segundo_turno():
    return _relatorio_paradas_motivo_turno_dia(1, 'RELATORIO DE PARADAS / MOTIVO 2º TURNO')

@app.route('/relatorio-paradas-motivo-terceiro-turno')
@login_required
@level_required([3, 5, 6])
def relatorio_paradas_motivo_terceiro_turno():
    return _relatorio_paradas_motivo_turno_dia(2, 'RELATORIO DE PARADAS / MOTIVO 3º TURNO')


def build_reason_daily_summary(
    db: sqlite3.Connection,
    start_date: str,
    end_date: str,
    shift_type_id: Optional[str],
):
    today = now_local().date()
    try:
        start_dt = datetime.date.fromisoformat(start_date)
        end_dt = datetime.date.fromisoformat(end_date)
    except Exception:
        start_dt = today - datetime.timedelta(days=7)
        end_dt = today
    if end_dt < start_dt:
        start_dt, end_dt = end_dt, start_dt

    now_dt = now_local()
    tzinfo = now_dt.tzinfo
    now_ref = now_dt.replace(tzinfo=None) if tzinfo else now_dt

    # days list
    days = []
    cur = start_dt
    while cur <= end_dt:
        days.append(cur)
        cur += datetime.timedelta(days=1)
    day_labels = [d.strftime('%d/%m') for d in days]

    # shift windows by weekday if shift_type_id provided
    windows_by_weekday = {}
    crosses_midnight = False
    if shift_type_id:
        rows = db.execute('SELECT * FROM shifts WHERE shift_type_id = ?', (int(shift_type_id),)).fetchall()
        for r in rows:
            wd = r['day']
            windows_by_weekday.setdefault(wd, []).append((r['start_1'], r['end_1']))
            try:
                s = datetime.datetime.strptime(r['start_1'], '%H:%M').time()
                e = datetime.datetime.strptime(r['end_1'], '%H:%M').time()
                if e <= s:
                    crosses_midnight = True
            except Exception:
                continue

    def db_weekday(py_date: datetime.date) -> int:
        return (py_date.weekday() + 1) % 7

    def to_local_naive(dt_obj: datetime.datetime) -> datetime.datetime:
        if dt_obj.tzinfo:
            return dt_obj.astimezone(tzinfo).replace(tzinfo=None) if tzinfo else dt_obj.replace(tzinfo=None)
        if tzinfo:
            return dt_obj.replace(tzinfo=tzinfo).astimezone(tzinfo).replace(tzinfo=None)
        return dt_obj

    def time_to_dt(date_obj, hhmm: str):
        t = datetime.datetime.strptime(hhmm, '%H:%M').time()
        return datetime.datetime.combine(date_obj, t)

    def build_windows_for_day(day_date, shifts_by_day):
        day_start = datetime.datetime.combine(day_date, datetime.time.min)
        day_end = day_start + datetime.timedelta(days=1)

        def intervals_for(base_date, shift_rows):
            for sh in shift_rows:
                start_str, end_str = sh
                if not start_str or not end_str:
                    continue
                start_t = datetime.datetime.strptime(start_str, '%H:%M').time()
                end_t = datetime.datetime.strptime(end_str, '%H:%M').time()
                start_dt_win = datetime.datetime.combine(base_date, start_t)
                end_dt_win = datetime.datetime.combine(base_date, end_t)
                if end_dt_win <= start_dt_win:
                    end_dt_win += datetime.timedelta(days=1)
                yield start_dt_win, end_dt_win

        windows = []
        weekday_db = db_weekday(day_date)
        current_shifts = shifts_by_day.get(weekday_db, [])
        prev_shifts = shifts_by_day.get((weekday_db - 1) % 7, [])

        for start_dt_win, end_dt_win in intervals_for(day_date, current_shifts):
            clip_start = max(start_dt_win, day_start)
            clip_end = min(end_dt_win, day_end)
            if now_ref and clip_end > now_ref:
                clip_end = now_ref
            if clip_end > clip_start:
                windows.append((clip_start, clip_end))

        prev_day = day_date - datetime.timedelta(days=1)
        for start_dt_win, end_dt_win in intervals_for(prev_day, prev_shifts):
            clip_start = max(start_dt_win, day_start)
            clip_end = min(end_dt_win, day_end)
            if now_ref and clip_end > now_ref:
                clip_end = now_ref
            if clip_end > clip_start:
                windows.append((clip_start, clip_end))
        return windows

    def overlap_minutes(a_start, a_end, b_start, b_end):
        start = max(a_start, b_start)
        end = min(a_end, b_end)
        if end <= start:
            return 0
        return int((end - start).total_seconds() // 60)

    # reason lookup
    reasons = {row['id']: row for row in db.execute('SELECT id, code, description FROM reasons').fetchall()}

    # pull status entries
    # determine min/max window span
    windows_all = []
    for d in days:
        windows_all.extend(build_windows_for_day(d, windows_by_weekday))
    if crosses_midnight:
        prev_day = start_dt - datetime.timedelta(days=1)
        windows_all.extend(build_windows_for_day(prev_day, windows_by_weekday))
    if windows_all:
        range_start = min(w[0] for w in windows_all)
        range_end = max(w[1] for w in windows_all)
        if now_ref:
            range_end = min(range_end, now_ref)
    else:
        range_start = datetime.datetime.combine(start_dt, datetime.time.min)
        raw_end = datetime.datetime.combine(end_dt + datetime.timedelta(days=1), datetime.time.min)
        range_end = min(raw_end, now_ref) if now_ref else raw_end
    st_rows = db.execute(
        '''SELECT reason_id, stop_time, start_time FROM status_tear
           WHERE stop_time IS NOT NULL
           AND stop_time < ?
           AND (start_time IS NULL OR start_time > ?)''',
        (range_end.isoformat(), range_start.isoformat()),
    ).fetchall()

    # Prepara janelas por dia (incluindo cortes por virada de dia)
    day_windows = []
    for d in days:
        if shift_type_id:
            day_windows.append(build_windows_for_day(d, windows_by_weekday))
        else:
            day_start = datetime.datetime.combine(d, datetime.time.min)
            day_end = day_start + datetime.timedelta(days=1)
            day_windows.append([(day_start, day_end)])

    summary = {}
    for row in st_rows:
        rid = row['reason_id']
        if not rid:
            continue
        if row['stop_time'] is None:
            continue
        try:
            stop_dt = datetime.datetime.fromisoformat(row['stop_time'])
            stop_dt = to_local_naive(stop_dt)
        except Exception:
            continue
        start_dt_row = None
        if row['start_time']:
            try:
                start_dt_row = datetime.datetime.fromisoformat(row['start_time'])
                start_dt_row = to_local_naive(start_dt_row)
            except Exception:
                start_dt_row = None
        end_dt_row = start_dt_row or range_end
        if end_dt_row <= range_start or stop_dt >= range_end:
            continue
        # clip to range
        if stop_dt < range_start:
            stop_dt = range_start
        if end_dt_row > range_end:
            end_dt_row = range_end

        start_clip = stop_dt
        end_clip = end_dt_row
        if end_clip <= start_clip:
            continue
        summary.setdefault(rid, {'values': [0] * len(days)})
        for idx, windows in enumerate(day_windows):
            for win_start, win_end in windows:
                minutes = overlap_minutes(start_clip, end_clip, win_start, win_end)
                if minutes > 0:
                    summary[rid]['values'][idx] += minutes

    report = []
    column_totals = [0] * len(days)
    grand_total = 0
    for rid, data in summary.items():
        rinfo = reasons.get(rid)
        code = rinfo['code'] if rinfo else '-'
        desc = rinfo['description'] if rinfo else '-'
        values = data['values']
        total = sum(values)
        for i, v in enumerate(values):
            column_totals[i] += v
        grand_total += total
        report.append({'code': code, 'description': desc, 'values': values, 'total': total})
    report.sort(key=lambda x: x['code'])

    # remove motivos com zero em todas as datas
    report = [row for row in report if row['total'] > 0]

    return {
        'report': report,
        'day_labels': day_labels,
        'column_totals': column_totals,
        'grand_total': grand_total,
        'start_date': start_dt.isoformat(),
        'end_date': end_dt.isoformat(),
        'selected_shift_type': shift_type_id or '',
    }
@app.route('/relatorio-motivos-final-semana')
@login_required
def relatorio_motivos_final_semana():
    flash('Relatorio motivos final de semana removido.', 'warning')
    return redirect(url_for('dashboard'))

@app.route('/relatoriogeral')
@login_required
@level_required([4, 5, 6])
def relatoriogeral():
    db = get_db()
    looms = db.execute('SELECT id, number FROM looms ORDER BY number').fetchall()
    shift_types = db.execute('SELECT id, name FROM shift_types WHERE id <> 4 ORDER BY name').fetchall()
    today = now_local().date()
    default_start = (today - datetime.timedelta(days=7)).isoformat()
    default_end = today.isoformat()
    start_date = request.args.get('start_date', default_start)
    end_date = request.args.get('end_date', default_end)
    status_filter = request.args.get('status', 'working')
    selected_looms = set(request.args.getlist('looms'))
    selected_shift_type = request.args.get('shift_type') or ''

    report_ctx = build_report_data(
        db,
        looms,
        shift_types,
        start_date,
        end_date,
        status_filter,
        selected_looms,
        selected_shift_type,
    )
    heatmap_data, day_labels = build_heatmap_data(
        db, looms, shift_types, start_date, end_date, selected_looms, selected_shift_type
    )
    return render_template(
        'relatoriogeral.html',
        looms=looms,
        shift_types=shift_types,
        heatmap_data=heatmap_data,
        **report_ctx,
    )

@app.route('/relatorio-primeiro-turno')
@login_required
@level_required([1, 5, 6])
def relatorio_primeiro_turno():
    db = get_db()
    looms = db.execute('SELECT id, number FROM looms ORDER BY number').fetchall()
    first_shift_type = db.execute('SELECT id, name FROM shift_types ORDER BY id LIMIT 1').fetchone()
    if not first_shift_type:
        flash('Nenhum tipo de turno cadastrado.', 'warning')
        return redirect(url_for('dashboard'))

    today = now_local().date()
    default_start = (today - datetime.timedelta(days=7)).isoformat()
    default_end = today.isoformat()
    start_date = request.args.get('start_date', default_start)
    end_date = request.args.get('end_date', default_end)
    status_filter = request.args.get('status', 'working')
    selected_looms = set(request.args.getlist('looms'))
    selected_shift_type = str(first_shift_type['id'])

    report_ctx = build_report_data(
        db,
        looms,
        [first_shift_type],
        start_date,
        end_date,
        status_filter,
        selected_looms,
        selected_shift_type,
    )
    heatmap_data, day_labels = build_heatmap_data(
        db, looms, [first_shift_type], start_date, end_date, selected_looms, selected_shift_type
    )
    return render_template(
        'relatorio_primeiro_turno.html',
        looms=looms,
        shift_type=first_shift_type,
        heatmap_data=heatmap_data,
        **report_ctx,
    )

@app.route('/relatorio-segundo-turno')
@login_required
@level_required([2, 5, 6])
def relatorio_segundo_turno():
    db = get_db()
    looms = db.execute('SELECT id, number FROM looms ORDER BY number').fetchall()
    second_shift_type = db.execute('SELECT id, name FROM shift_types ORDER BY id LIMIT 1 OFFSET 1').fetchone()
    if not second_shift_type:
        flash('Nenhum segundo tipo de turno cadastrado.', 'warning')
        return redirect(url_for('dashboard'))

    today = now_local().date()
    default_start = (today - datetime.timedelta(days=7)).isoformat()
    default_end = today.isoformat()
    start_date = request.args.get('start_date', default_start)
    end_date = request.args.get('end_date', default_end)
    status_filter = request.args.get('status', 'working')
    selected_looms = set(request.args.getlist('looms'))
    selected_shift_type = str(second_shift_type['id'])

    report_ctx = build_report_data(
        db,
        looms,
        [second_shift_type],
        start_date,
        end_date,
        status_filter,
        selected_looms,
        selected_shift_type,
    )
    heatmap_data, day_labels = build_heatmap_data(
        db, looms, [second_shift_type], start_date, end_date, selected_looms, selected_shift_type
    )
    return render_template(
        'relatorio_segundo_turno.html',
        looms=looms,
        shift_type=second_shift_type,
        heatmap_data=heatmap_data,
        **report_ctx,
    )

@app.route('/relatorio-terceiro-turno')
@login_required
@level_required([3, 5, 6])
def relatorio_terceiro_turno():
    db = get_db()
    looms = db.execute('SELECT id, number FROM looms ORDER BY number').fetchall()
    third_shift_type = db.execute('SELECT id, name FROM shift_types ORDER BY id LIMIT 1 OFFSET 2').fetchone()
    if not third_shift_type:
        flash('Nenhum terceiro tipo de turno cadastrado.', 'warning')
        return redirect(url_for('dashboard'))

    today = now_local().date()
    default_start = (today - datetime.timedelta(days=7)).isoformat()
    default_end = today.isoformat()
    start_date = request.args.get('start_date', default_start)
    end_date = request.args.get('end_date', default_end)
    status_filter = request.args.get('status', 'working')
    selected_looms = set(request.args.getlist('looms'))
    selected_shift_type = str(third_shift_type['id'])

    report_ctx = build_report_data(
        db,
        looms,
        [third_shift_type],
        start_date,
        end_date,
        status_filter,
        selected_looms,
        selected_shift_type,
    )
    heatmap_data, day_labels = build_heatmap_data(
        db, looms, [third_shift_type], start_date, end_date, selected_looms, selected_shift_type
    )
    return render_template(
        'relatorio_terceiro_turno.html',
        looms=looms,
        shift_type=third_shift_type,
        heatmap_data=heatmap_data,
        **report_ctx,
    )


@app.route('/reasons/new', methods=['GET', 'POST'])
@login_required
@level_required([5, 6])
def reasons_create():
    if request.method == 'POST':
        code = request.form.get('code')
        description = request.form.get('description')
        if not code or not description:
            flash('Código e descrição são obrigatórios.', 'danger')
        else:
            db = get_db()
            try:
                db.execute('INSERT INTO reasons (code, description) VALUES (?, ?)', (int(code), description))
                db.commit()
                flash('Motivo criado.', 'success')
                return redirect(url_for('reasons_list'))
            except sqlite3.IntegrityError:
                flash('Código já existe.', 'danger')
            except ValueError:
                flash('Código deve ser numérico.', 'danger')
    return render_template('reason_form.html', action_url=url_for('reasons_create'), reason=None)


@app.route('/reasons/<int:reason_id>/edit', methods=['GET', 'POST'])
@login_required
@level_required([5, 6])
def reasons_edit(reason_id):
    db = get_db()
    reason = db.execute('SELECT * FROM reasons WHERE id = ?', (reason_id,)).fetchone()
    if not reason:
        flash('Motivo não encontrado.', 'danger')
        return redirect(url_for('reasons_list'))

    if request.method == 'POST':
        code = request.form.get('code')
        description = request.form.get('description')
        if not code or not description:
            flash('Código e descrição são obrigatórios.', 'danger')
        else:
            try:
                db.execute('UPDATE reasons SET code = ?, description = ? WHERE id = ?', (int(code), description, reason_id))
                db.commit()
                flash('Motivo atualizado.', 'success')
                return redirect(url_for('reasons_list'))
            except sqlite3.IntegrityError:
                flash('Código já existe.', 'danger')
            except ValueError:
                flash('Código deve ser numérico.', 'danger')
    return render_template('reason_form.html', action_url=url_for('reasons_edit', reason_id=reason_id), reason=reason)


@app.route('/reasons/<int:reason_id>/delete', methods=['POST'])
@login_required
@level_required([5, 6])
def reasons_delete(reason_id):
    db = get_db()
    db.execute('DELETE FROM reasons WHERE id = ?', (reason_id,))
    db.commit()
    flash('Motivo removido.', 'info')
    return redirect(url_for('reasons_list'))


# --- Dashboard teares ---
@app.route('/dashboard-teares')
@login_required
def dashboard_teares():
    ctx = build_dashboard_teares_context()
    return render_template('dashboard_teares.html', **ctx)

def validate_shift_time(shift_id: int, time_str: str, db: sqlite3.Connection) -> bool:
    shift = db.execute('SELECT * FROM shifts WHERE id = ?', (shift_id,)).fetchone()
    if not shift:
        return False
    return time_in_shift(time_str, shift)


def build_report_data(
    db: sqlite3.Connection,
    looms,
    shift_types,
    start_date: str,
    end_date: str,
    status_filter: str,
    selected_looms,
    selected_shift_type: str,
):
    today = now_local().date()
    try:
        start_dt = datetime.date.fromisoformat(start_date)
        end_dt = datetime.date.fromisoformat(end_date)
    except Exception:
        start_dt = today - datetime.timedelta(days=7)
        end_dt = today
    if end_dt < start_dt:
        start_dt, end_dt = end_dt, start_dt

    now_dt = now_local()
    tzinfo = now_dt.tzinfo
    now_ref = now_dt.replace(tzinfo=None) if tzinfo else now_dt

    def to_local_naive(dt_obj: datetime.datetime) -> datetime.datetime:
        if dt_obj.tzinfo:
            return dt_obj.astimezone(tzinfo).replace(tzinfo=None) if tzinfo else dt_obj.replace(tzinfo=None)
        if tzinfo:
            return dt_obj.replace(tzinfo=tzinfo).astimezone(tzinfo).replace(tzinfo=None)
        return dt_obj

    def daterange(start_d, end_d):
        curr = start_d
        while curr <= end_d:
            yield curr
            curr += datetime.timedelta(days=1)

    range_start = datetime.datetime.combine(start_dt, datetime.time.min)
    range_end = datetime.datetime.combine(end_dt + datetime.timedelta(days=1), datetime.time.min)
    if range_end > now_ref:
        range_end = now_ref

    loom_ids = [str(l['id']) for l in looms]
    filter_looms = selected_looms if selected_looms else set(loom_ids)

    # Helper para alinhar weekday Python (segunda=0) com base de dados (domingo=0)
    def db_day_index(py_date: datetime.date) -> int:
        return (py_date.weekday() + 1) % 7

    # Pré-carrega turnos por weekday quando filtrando por turno
    shifts_by_day = {}
    if selected_shift_type:
        rows = db.execute(
            'SELECT * FROM shifts WHERE shift_type_id = ?', (int(selected_shift_type),)
        ).fetchall()
        for r in rows:
            shifts_by_day.setdefault(r['day'], []).append(r)

    def build_windows(day_date):
        day_start = datetime.datetime.combine(day_date, datetime.time.min)
        day_end = day_start + datetime.timedelta(days=1)
        if not selected_shift_type:
            return [(day_start, min(day_end, now_ref))]

        def intervals_for(base_date, shift_rows):
            for sh in shift_rows:
                start_str, end_str = sh['start_1'], sh['end_1']
                if not start_str or not end_str:
                    continue
                start_t = datetime.datetime.strptime(start_str, '%H:%M').time()
                end_t = datetime.datetime.strptime(end_str, '%H:%M').time()
                start_dt_win = datetime.datetime.combine(base_date, start_t)
                end_dt_win = datetime.datetime.combine(base_date, end_t)
                if end_dt_win <= start_dt_win:
                    end_dt_win += datetime.timedelta(days=1)
                yield start_dt_win, end_dt_win

        windows = []
        weekday_db = db_day_index(day_date)
        current_shifts = shifts_by_day.get(weekday_db, [])
        prev_shifts = shifts_by_day.get((weekday_db - 1) % 7, [])

        for start_dt_win, end_dt_win in intervals_for(day_date, current_shifts):
            clip_start = max(start_dt_win, day_start)
            clip_end = min(end_dt_win, day_end)
            if clip_end > clip_start:
                windows.append((clip_start, clip_end))

        prev_day = day_date - datetime.timedelta(days=1)
        for start_dt_win, end_dt_win in intervals_for(prev_day, prev_shifts):
            clip_start = max(start_dt_win, day_start)
            clip_end = min(end_dt_win, day_end)
            if clip_end > clip_start:
                windows.append((clip_start, clip_end))
        return windows

    def overlap_minutes(a_start, a_end, b_start, b_end):
        start = max(a_start, b_start)
        end = min(a_end, b_end)
        if end <= start:
            return 0
        return int((end - start).total_seconds() // 60)

    st_rows = db.execute(
        'SELECT loom_id, stop_time, start_time FROM status_tear WHERE loom_id IN ({}) ORDER BY stop_time'.format(
            ','.join(['?'] * len(filter_looms))
        ),
        tuple(filter_looms),
    ).fetchall() if filter_looms else []

    downtime_by_loom = {int(lid): [] for lid in filter_looms}
    for row in st_rows:
        if not row['stop_time']:
            continue
        try:
            stop_dt_raw = datetime.datetime.fromisoformat(row['stop_time'])
        except Exception:
            continue
        stop_dt = to_local_naive(stop_dt_raw)
        start_dt_row = None
        if row['start_time']:
            try:
                start_dt_raw = datetime.datetime.fromisoformat(row['start_time'])
                start_dt_row = to_local_naive(start_dt_raw)
            except Exception:
                start_dt_row = None
        end_dt_interval = start_dt_row or range_end
        if end_dt_interval <= range_start or stop_dt >= range_end:
            continue
        start_clip = max(stop_dt, range_start)
        end_clip = min(end_dt_interval, range_end)
        if end_clip > start_clip:
            downtime_by_loom[int(row['loom_id'])].append((start_clip, end_clip))

    report_days = list(daterange(start_dt, end_dt))
    report = []
    for l in looms:
        if str(l['id']) not in filter_looms:
            continue
        per_day = []
        total_minutes = 0
        for day in report_days:
            windows = build_windows(day)
            day_total_minutes = 0
            day_downtime = 0
            for win_start, win_end in windows:
                if day < now_ref.date():
                    win_effective_end = win_end
                else:
                    win_effective_end = min(win_end, now_ref)
                if win_effective_end <= win_start:
                    continue
                window_minutes = int((win_effective_end - win_start).total_seconds() // 60)
                day_total_minutes += window_minutes
                for d_start, d_end in downtime_by_loom.get(l['id'], []):
                    day_downtime += overlap_minutes(d_start, d_end, win_start, win_effective_end)
            if status_filter == 'stopped':
                minutes_val = day_downtime
            else:
                minutes_val = max(day_total_minutes - day_downtime, 0)
            per_day.append(minutes_val)
            total_minutes += minutes_val
        report.append({'loom': l, 'values': per_day, 'total': total_minutes})

    day_labels = [d.strftime('%d/%m') for d in report_days]
    column_totals = []
    if report:
        num_days = len(report_days)
        column_totals = [0] * num_days
        for row in report:
            for idx, minutes_val in enumerate(row['values']):
                column_totals[idx] += minutes_val
    grand_total = sum(row['total'] for row in report)
    return {
        'report': report,
        'day_labels': day_labels,
        'column_totals': column_totals,
        'grand_total': grand_total,
        'start_date': start_dt.isoformat(),
        'end_date': end_dt.isoformat(),
        'status_filter': status_filter,
        'selected_looms': selected_looms,
        'selected_shift_type': selected_shift_type,
    }


def build_reason_report_data(
    db: sqlite3.Connection,
    looms,
    shift_types,
    reasons,
    start_date: str,
    end_date: str,
    selected_loom: str,
    selected_shift_type: str,
):
    today = now_local().date()
    try:
        start_dt = datetime.date.fromisoformat(start_date)
        end_dt = datetime.date.fromisoformat(end_date)
    except Exception:
        start_dt = today - datetime.timedelta(days=7)
        end_dt = today
    if end_dt < start_dt:
        start_dt, end_dt = end_dt, start_dt

    now_dt = now_local()
    tzinfo = now_dt.tzinfo
    now_ref = now_dt.replace(tzinfo=None) if tzinfo else now_dt

    def to_local_naive(dt_obj: datetime.datetime) -> datetime.datetime:
        if dt_obj.tzinfo:
            return dt_obj.astimezone(tzinfo).replace(tzinfo=None) if tzinfo else dt_obj.replace(tzinfo=None)
        if tzinfo:
            return dt_obj.replace(tzinfo=tzinfo).astimezone(tzinfo).replace(tzinfo=None)
        return dt_obj

    def daterange(start_d, end_d):
        curr = start_d
        while curr <= end_d:
            yield curr
            curr += datetime.timedelta(days=1)

    range_start = datetime.datetime.combine(start_dt, datetime.time.min)
    range_end = datetime.datetime.combine(end_dt + datetime.timedelta(days=1), datetime.time.min)
    if range_end > now_ref:
        range_end = now_ref

    loom_ids = [str(l['id']) for l in looms]
    loom_id = selected_loom if selected_loom else (loom_ids[0] if loom_ids else None)
    if loom_id and str(loom_id) not in loom_ids:
        loom_id = loom_ids[0] if loom_ids else None
    if not loom_id:
        return {
            'report': [],
            'day_labels': [],
            'column_totals': [],
            'grand_total': 0,
            'start_date': start_dt.isoformat(),
            'end_date': end_dt.isoformat(),
            'selected_loom': '',
            'selected_shift_types': selected_shift_types,
        }

    available_shift_ids = {str(st['id']) for st in shift_types}
    shift_filter = set()
    if selected_shift_type and selected_shift_type in available_shift_ids:
        shift_filter = {selected_shift_type}
    else:
        shift_filter = available_shift_ids

    def db_day_index(py_date: datetime.date) -> int:
        return (py_date.weekday() + 1) % 7

    shifts_by_day = {}
    if shift_filter:
        placeholders = ','.join(['?'] * len(shift_filter))
        rows = db.execute(
            f'SELECT * FROM shifts WHERE shift_type_id IN ({placeholders})',
            tuple(shift_filter),
        ).fetchall()
        for r in rows:
            shifts_by_day.setdefault(r['day'], []).append(r)

    def build_windows(day_date):
        day_start = datetime.datetime.combine(day_date, datetime.time.min)
        day_end = day_start + datetime.timedelta(days=1)
        if not shifts_by_day:
            return [(day_start, min(day_end, now_ref))]

        def intervals_for(base_date, shift_rows):
            for sh in shift_rows:
                start_str, end_str = sh['start_1'], sh['end_1']
                if not start_str or not end_str:
                    continue
                start_t = datetime.datetime.strptime(start_str, '%H:%M').time()
                end_t = datetime.datetime.strptime(end_str, '%H:%M').time()
                start_dt_win = datetime.datetime.combine(base_date, start_t)
                end_dt_win = datetime.datetime.combine(base_date, end_t)
                if end_dt_win <= start_dt_win:
                    end_dt_win += datetime.timedelta(days=1)
                yield start_dt_win, end_dt_win

        windows = []
        weekday_db = db_day_index(day_date)
        current_shifts = shifts_by_day.get(weekday_db, [])
        prev_shifts = shifts_by_day.get((weekday_db - 1) % 7, [])

        for start_dt_win, end_dt_win in intervals_for(day_date, current_shifts):
            clip_start = max(start_dt_win, day_start)
            clip_end = min(end_dt_win, day_end)
            if clip_end > clip_start:
                windows.append((clip_start, clip_end))

        prev_day = day_date - datetime.timedelta(days=1)
        for start_dt_win, end_dt_win in intervals_for(prev_day, prev_shifts):
            clip_start = max(start_dt_win, day_start)
            clip_end = min(end_dt_win, day_end)
            if clip_end > clip_start:
                windows.append((clip_start, clip_end))
        return windows

    def overlap_minutes(a_start, a_end, b_start, b_end):
        start = max(a_start, b_start)
        end = min(a_end, b_end)
        if end <= start:
            return 0
        return int((end - start).total_seconds() // 60)

    st_rows = db.execute(
        'SELECT reason_id, stop_time, start_time FROM status_tear WHERE loom_id = ? ORDER BY stop_time',
        (int(loom_id),),
    ).fetchall()

    downtime_by_reason = {}
    for row in st_rows:
        if not row['stop_time']:
            continue
        try:
            stop_dt_raw = datetime.datetime.fromisoformat(row['stop_time'])
        except Exception:
            continue
        stop_dt = to_local_naive(stop_dt_raw)
        start_dt_row = None
        if row['start_time']:
            try:
                start_dt_raw = datetime.datetime.fromisoformat(row['start_time'])
                start_dt_row = to_local_naive(start_dt_raw)
            except Exception:
                start_dt_row = None
        end_dt_interval = start_dt_row or range_end
        if end_dt_interval <= range_start or stop_dt >= range_end:
            continue
        start_clip = max(stop_dt, range_start)
        end_clip = min(end_dt_interval, range_end)
        if end_clip > start_clip:
            rid = row['reason_id']
            downtime_by_reason.setdefault(rid, []).append((start_clip, end_clip))

    report_days = list(daterange(start_dt, end_dt))
    report = []
    # Chart helpers
    def merge_intervals(intervals):
        if not intervals:
            return []
        intervals = sorted(intervals, key=lambda x: x[0])
        merged = [intervals[0]]
        for start, end in intervals[1:]:
            last_start, last_end = merged[-1]
            if start <= last_end:
                merged[-1] = (last_start, max(last_end, end))
            else:
                merged.append((start, end))
        return merged

    day_windows = []
    daily_window_minutes = []
    for day in report_days:
        windows = build_windows(day)
        adjusted = []
        for win_start, win_end in windows:
            win_effective_end = min(win_end, now_ref) if day >= now_ref.date() else win_end
            if win_effective_end > win_start:
                adjusted.append((win_start, win_effective_end))
        merged = merge_intervals(adjusted)
        total_minutes = sum(int((e - s).total_seconds() // 60) for s, e in merged)
        day_windows.append(merged)
        daily_window_minutes.append(total_minutes)

    daily_downtime_minutes = [0] * len(report_days)
    for reason in reasons:
        per_day = []
        total_minutes = 0
        intervals = downtime_by_reason.get(reason['id'], [])
        for idx, day in enumerate(report_days):
            windows = day_windows[idx]
            day_total = 0
            for win_start, win_end in windows:
                for d_start, d_end in intervals:
                    day_total += overlap_minutes(d_start, d_end, win_start, win_end)
            per_day.append(day_total)
            total_minutes += day_total
            daily_downtime_minutes[idx] += day_total
        report.append({'reason': reason, 'values': per_day, 'total': total_minutes})

    report = [row for row in report if row['total'] > 0]

    day_labels = [d.strftime('%d/%m') for d in report_days]
    column_totals = []
    if report:
        num_days = len(report_days)
        column_totals = [0] * num_days
        for row in report:
            for idx, minutes_val in enumerate(row['values']):
                column_totals[idx] += minutes_val
    grand_total = sum(row['total'] for row in report)

    daily_running_minutes = [
        max(total - down, 0) for total, down in zip(daily_window_minutes, daily_downtime_minutes)
    ]
    max_window_hours = max(daily_window_minutes) / 60 if daily_window_minutes else 0
    if selected_shift_type:
        chart_max_hours = min(12, max(1, max_window_hours + 1))
    else:
        chart_max_hours = min(28, max(1, max_window_hours + 2))

    return {
        'report': report,
        'day_labels': day_labels,
        'column_totals': column_totals,
        'grand_total': grand_total,
        'chart_labels': day_labels,
        'chart_downtime': daily_downtime_minutes,
        'chart_running': daily_running_minutes,
        'chart_max_hours': chart_max_hours,
        'start_date': start_dt.isoformat(),
        'end_date': end_dt.isoformat(),
        'selected_loom': str(loom_id),
        'selected_shift_type': selected_shift_type if selected_shift_type in available_shift_ids else '',
        'selected_loom_label': next((f"Tear {l['number']}" for l in looms if str(l['id']) == str(loom_id)), 'Tear selecionado'),
    }


def build_weekend_report_data(
    db: sqlite3.Connection,
    looms,
    rodizio_types,
    start_date: str,
    end_date: str,
    status_filter: str,
    selected_looms,
):
    today = now_local().date()
    try:
        start_dt = datetime.date.fromisoformat(start_date)
        end_dt = datetime.date.fromisoformat(end_date)
    except Exception:
        start_dt = today - datetime.timedelta(days=14)
        end_dt = today
    if end_dt < start_dt:
        start_dt, end_dt = end_dt, start_dt

    now_dt = now_local()
    tzinfo = now_dt.tzinfo
    now_ref = now_dt.replace(tzinfo=None) if tzinfo else now_dt

    def to_local_naive(dt_obj: datetime.datetime) -> datetime.datetime:
        if dt_obj.tzinfo:
            return dt_obj.astimezone(tzinfo).replace(tzinfo=None) if tzinfo else dt_obj.replace(tzinfo=None)
        if tzinfo:
            return dt_obj.replace(tzinfo=tzinfo).astimezone(tzinfo).replace(tzinfo=None)
        return dt_obj

    def db_day_index(py_date: datetime.date) -> int:
        return (py_date.weekday() + 1) % 7

    weekend_intervals = []
    cur = start_dt
    while cur <= end_dt:
        if cur.weekday() == 5:  # Saturday
            sat = cur
            sun = cur + datetime.timedelta(days=1)
            start_win = datetime.datetime.combine(sat, datetime.time(13, 0))
            end_win = datetime.datetime.combine(sun, datetime.time(22, 0))
            weekend_intervals.append((start_win, end_win))
            cur = cur + datetime.timedelta(days=7)
        else:
            cur += datetime.timedelta(days=1)

    if not weekend_intervals:
        return {
            'report': [],
            'rodizio_labels': [rt['name'] for rt in rodizio_types],
            'start_date': start_dt.isoformat(),
            'end_date': end_dt.isoformat(),
            'status_filter': status_filter,
            'selected_looms': selected_looms,
        }

    range_start = weekend_intervals[0][0]
    range_end = weekend_intervals[-1][1]
    if range_end > now_ref:
        range_end = now_ref

    loom_ids = [str(l['id']) for l in looms]
    filter_looms = selected_looms if selected_looms else set(loom_ids)

    st_rows = db.execute(
        'SELECT loom_id, stop_time, start_time FROM status_tear WHERE loom_id IN ({}) ORDER BY stop_time'.format(
            ','.join(['?'] * len(filter_looms))
        ),
        tuple(filter_looms),
    ).fetchall() if filter_looms else []

    downtime_by_loom = {int(lid): [] for lid in filter_looms}
    for row in st_rows:
        if not row['stop_time']:
            continue
        try:
            stop_dt_raw = datetime.datetime.fromisoformat(row['stop_time'])
        except Exception:
            continue
        stop_dt = to_local_naive(stop_dt_raw)
        start_dt_row = None
        if row['start_time']:
            try:
                start_dt_raw = datetime.datetime.fromisoformat(row['start_time'])
                start_dt_row = to_local_naive(start_dt_raw)
            except Exception:
                start_dt_row = None
        end_dt_interval = start_dt_row or range_end
        if end_dt_interval <= range_start or stop_dt >= range_end:
            continue
        start_clip = max(stop_dt, range_start)
        end_clip = min(end_dt_interval, range_end)
        if end_clip > start_clip:
            downtime_by_loom[int(row['loom_id'])].append((start_clip, end_clip))

    def build_windows_for_day(day_date, shifts_by_day):
        day_start = datetime.datetime.combine(day_date, datetime.time.min)
        day_end = day_start + datetime.timedelta(days=1)
        def intervals_for(base_date, shift_rows):
            for sh in shift_rows:
                start_str, end_str = sh['start_1'], sh['end_1']
                if not start_str or not end_str:
                    continue
                start_t = datetime.datetime.strptime(start_str, '%H:%M').time()
                end_t = datetime.datetime.strptime(end_str, '%H:%M').time()
                start_dt_win = datetime.datetime.combine(base_date, start_t)
                end_dt_win = datetime.datetime.combine(base_date, end_t)
                if end_dt_win <= start_dt_win:
                    end_dt_win += datetime.timedelta(days=1)
                yield start_dt_win, end_dt_win
        windows = []
        weekday_db = db_day_index(day_date)
        current_shifts = shifts_by_day.get(weekday_db, [])
        prev_shifts = shifts_by_day.get((weekday_db - 1) % 7, [])
        for start_dt_win, end_dt_win in intervals_for(day_date, current_shifts):
            clip_start = max(start_dt_win, day_start)
            clip_end = min(end_dt_win, day_end)
            if clip_end > clip_start:
                windows.append((clip_start, clip_end))
        prev_day = day_date - datetime.timedelta(days=1)
        for start_dt_win, end_dt_win in intervals_for(prev_day, prev_shifts):
            clip_start = max(start_dt_win, day_start)
            clip_end = min(end_dt_win, day_end)
            if clip_end > clip_start:
                windows.append((clip_start, clip_end))
        return windows

    report = []
    for l in looms:
        if str(l['id']) not in filter_looms:
            continue
        per_rodizio = []
        total_minutes = 0
        for rod in rodizio_types:
            shifts_by_day = {}
            rows = db.execute(
                'SELECT * FROM shifts WHERE shift_type_id = ?', (rod['id'],)
            ).fetchall()
            for r in rows:
                shifts_by_day.setdefault(r['day'], []).append(r)

            rod_minutes = 0
            for wk_start, wk_end in weekend_intervals:
                wk_end_eff = min(wk_end, now_ref)
                if wk_end_eff <= wk_start:
                    continue
                for day in (wk_start.date(), wk_start.date() + datetime.timedelta(days=1)):
                    windows = build_windows_for_day(day, shifts_by_day)
                    for win_start, win_end in windows:
                        win_clip_start = max(win_start, wk_start)
                        win_clip_end = min(win_end, wk_end_eff)
                        if win_clip_end <= win_clip_start:
                            continue
                        window_minutes = int((win_clip_end - win_clip_start).total_seconds() // 60)
                        downtime = 0
                        for d_start, d_end in downtime_by_loom.get(l['id'], []):
                            start = max(d_start, win_clip_start)
                            end = min(d_end, win_clip_end)
                            if end > start:
                                downtime += int((end - start).total_seconds() // 60)
                        if status_filter == 'stopped':
                            rod_minutes += downtime
                        else:
                            rod_minutes += max(window_minutes - downtime, 0)
            per_rodizio.append(rod_minutes)
            total_minutes += rod_minutes
        report.append({'loom': l, 'values': per_rodizio, 'total': total_minutes})

    column_totals = []
    if report:
        num_cols = len(report[0]['values'])
        column_totals = [0] * num_cols
        for row in report:
            for idx, minutes_val in enumerate(row['values']):
                column_totals[idx] += minutes_val
    grand_total = sum(row['total'] for row in report)

    return {
        'report': report,
        'rodizio_labels': [rt['name'] for rt in rodizio_types],
        'column_totals': column_totals,
        'grand_total': grand_total,
        'start_date': start_dt.isoformat(),
        'end_date': end_dt.isoformat(),
        'status_filter': status_filter,
        'selected_looms': selected_looms,
    }


def build_weekend_reason_report_data(
    db: sqlite3.Connection,
    looms,
    rodizio_types,
    reasons,
    start_date: str,
    end_date: str,
    status_filter: str,
    selected_looms,
):
    today = now_local().date()
    try:
        start_dt = datetime.date.fromisoformat(start_date)
        end_dt = datetime.date.fromisoformat(end_date)
    except Exception:
        start_dt = today - datetime.timedelta(days=14)
        end_dt = today
    if end_dt < start_dt:
        start_dt, end_dt = end_dt, start_dt

    now_dt = now_local()
    tzinfo = now_dt.tzinfo
    now_ref = now_dt.replace(tzinfo=None) if tzinfo else now_dt

    def to_local_naive(dt_obj: datetime.datetime) -> datetime.datetime:
        if dt_obj.tzinfo:
            return dt_obj.astimezone(tzinfo).replace(tzinfo=None) if tzinfo else dt_obj.replace(tzinfo=None)
        if tzinfo:
            return dt_obj.replace(tzinfo=tzinfo).astimezone(tzinfo).replace(tzinfo=None)
        return dt_obj

    def db_day_index(py_date: datetime.date) -> int:
        return (py_date.weekday() + 1) % 7

    weekend_intervals = []
    cur = start_dt
    while cur <= end_dt:
        if cur.weekday() == 5:  # Saturday
            sat = cur
            sun = cur + datetime.timedelta(days=1)
            start_win = datetime.datetime.combine(sat, datetime.time(13, 0))
            end_win = datetime.datetime.combine(sun, datetime.time(22, 0))
            weekend_intervals.append((start_win, end_win))
            cur = cur + datetime.timedelta(days=7)
        else:
            cur += datetime.timedelta(days=1)

    if not weekend_intervals:
        return {
            'report': [],
            'rodizio_labels': [rt['name'] for rt in rodizio_types],
            'column_totals': [],
            'grand_total': 0,
            'start_date': start_dt.isoformat(),
            'end_date': end_dt.isoformat(),
            'status_filter': status_filter,
            'selected_looms': selected_looms,
        }

    range_start = weekend_intervals[0][0]
    range_end = weekend_intervals[-1][1]
    if range_end > now_ref:
        range_end = now_ref

    loom_ids = [str(l['id']) for l in looms]
    chosen_loom = None
    if selected_looms:
        chosen_loom = next(iter(selected_looms))
    elif loom_ids:
        chosen_loom = loom_ids[0]
    filter_looms = {chosen_loom} if chosen_loom else set()

    st_rows = db.execute(
        'SELECT loom_id, reason_id, stop_time, start_time FROM status_tear WHERE loom_id IN ({}) ORDER BY stop_time'.format(
            ','.join(['?'] * len(filter_looms))
        ),
        tuple(filter_looms),
    ).fetchall() if filter_looms else []

    downtime_by_reason = {}
    for row in st_rows:
        if not row['stop_time']:
            continue
        try:
            stop_dt_raw = datetime.datetime.fromisoformat(row['stop_time'])
        except Exception:
            continue
        stop_dt = to_local_naive(stop_dt_raw)
        start_dt_row = None
        if row['start_time']:
            try:
                start_dt_raw = datetime.datetime.fromisoformat(row['start_time'])
                start_dt_row = to_local_naive(start_dt_raw)
            except Exception:
                start_dt_row = None
        end_dt_interval = start_dt_row or range_end
        if end_dt_interval <= range_start or stop_dt >= range_end:
            continue
        start_clip = max(stop_dt, range_start)
        end_clip = min(end_dt_interval, range_end)
        if end_clip > start_clip:
            rid = row['reason_id']
            downtime_by_reason.setdefault(rid, []).append((start_clip, end_clip))

    def build_windows_for_day(day_date, shifts_by_day):
        day_start = datetime.datetime.combine(day_date, datetime.time.min)
        day_end = day_start + datetime.timedelta(days=1)
        def intervals_for(base_date, shift_rows):
            for sh in shift_rows:
                start_str, end_str = sh['start_1'], sh['end_1']
                if not start_str or not end_str:
                    continue
                start_t = datetime.datetime.strptime(start_str, '%H:%M').time()
                end_t = datetime.datetime.strptime(end_str, '%H:%M').time()
                start_dt_win = datetime.datetime.combine(base_date, start_t)
                end_dt_win = datetime.datetime.combine(base_date, end_t)
                if end_dt_win <= start_dt_win:
                    end_dt_win += datetime.timedelta(days=1)
                yield start_dt_win, end_dt_win
        windows = []
        weekday_db = db_day_index(day_date)
        current_shifts = shifts_by_day.get(weekday_db, [])
        prev_shifts = shifts_by_day.get((weekday_db - 1) % 7, [])
        for start_dt_win, end_dt_win in intervals_for(day_date, current_shifts):
            clip_start = max(start_dt_win, day_start)
            clip_end = min(end_dt_win, day_end)
            if clip_end > clip_start:
                windows.append((clip_start, clip_end))
        prev_day = day_date - datetime.timedelta(days=1)
        for start_dt_win, end_dt_win in intervals_for(prev_day, prev_shifts):
            clip_start = max(start_dt_win, day_start)
            clip_end = min(end_dt_win, day_end)
            if clip_end > clip_start:
                windows.append((clip_start, clip_end))
        return windows

    report = []
    rodizio_window_minutes = [0] * len(rodizio_types)
    for reason in reasons:
        per_rodizio = []
        total_minutes = 0
        for r_idx, rod in enumerate(rodizio_types):
            shifts_by_day = {}
            rows = db.execute(
                'SELECT * FROM shifts WHERE shift_type_id = ?', (rod['id'],)
            ).fetchall()
            for r in rows:
                shifts_by_day.setdefault(r['day'], []).append(r)

            rod_minutes = 0
            for wk_start, wk_end in weekend_intervals:
                wk_end_eff = min(wk_end, now_ref)
                if wk_end_eff <= wk_start:
                    continue
                # accumulate window minutes for this rodizio (once per rodizio)
                win_total_this_interval = 0
                for day in (wk_start.date(), wk_start.date() + datetime.timedelta(days=1)):
                    windows = build_windows_for_day(day, shifts_by_day)
                    for win_start, win_end in windows:
                        win_clip_start = max(win_start, wk_start)
                        win_clip_end = min(win_end, wk_end_eff)
                        if win_clip_end <= win_clip_start:
                            continue
                        window_minutes = int((win_clip_end - win_clip_start).total_seconds() // 60)
                        win_total_this_interval += window_minutes
                        downtime = 0
                        for d_start, d_end in downtime_by_reason.get(reason['id'], []):
                            start = max(d_start, win_clip_start)
                            end = min(d_end, win_clip_end)
                            if end > start:
                                downtime += int((end - start).total_seconds() // 60)
                        if status_filter == 'stopped':
                            rod_minutes += downtime
                        else:
                            rod_minutes += max(window_minutes - downtime, 0)
                rodizio_window_minutes[r_idx] += win_total_this_interval
            per_rodizio.append(rod_minutes)
            total_minutes += rod_minutes
        if total_minutes > 0:
            report.append({'reason': reason, 'values': per_rodizio, 'total': total_minutes})

    rodizio_labels = [rt['name'] for rt in rodizio_types]
    column_totals = []
    if report:
        num_cols = len(rodizio_labels)
        column_totals = [0] * num_cols
        for row in report:
            for idx, minutes_val in enumerate(row['values']):
                column_totals[idx] += minutes_val
    grand_total = sum(row['total'] for row in report)
    chart_downtime = column_totals
    chart_running = [max(w - d, 0) for w, d in zip(rodizio_window_minutes, chart_downtime)] if rodizio_window_minutes else []

    return {
        'report': report,
        'rodizio_labels': rodizio_labels,
        'column_totals': column_totals,
        'grand_total': grand_total,
        'chart_labels': rodizio_labels,
        'chart_downtime': chart_downtime,
        'chart_running': chart_running,
        'start_date': start_dt.isoformat(),
        'end_date': end_dt.isoformat(),
        'status_filter': status_filter,
        'selected_looms': filter_looms,
    }



def export_api_for_shift(shift_id: int, for_date: Optional[datetime.date] = None, clear_existing: bool = False) -> int:
    """Gera linhas na tabela api (api.db) para um turno, cortando o intervalo de parada dentro da janela do turno."""
    db = get_db()
    shift_row = db.execute(
        '''SELECT sh.*, st.name AS shift_name
           FROM shifts sh
           LEFT JOIN shift_types st ON st.id = sh.shift_type_id
           WHERE sh.id = ?''',
        (shift_id,),
    ).fetchone()
    if not shift_row or not shift_row['start_1'] or not shift_row['end_1']:
        return 0

    shift_day = for_date or now_local().date()  # dia de início do turno
    try:
        start_t = datetime.datetime.strptime(shift_row['start_1'], '%H:%M').time()
        end_t = datetime.datetime.strptime(shift_row['end_1'], '%H:%M').time()
    except Exception:
        return 0

    shift_start = datetime.datetime.combine(shift_day, start_t)
    shift_end = datetime.datetime.combine(shift_day, end_t)
    windows = []
    if shift_end <= shift_start:
        next_day = shift_day + datetime.timedelta(days=1)
        # Janela de 22:00-23:59 do dia selecionado e 00:00-05:00 do dia seguinte
        windows.append((shift_start, datetime.datetime.combine(next_day, datetime.time(0, 0))))
        windows.append((datetime.datetime.combine(next_day, datetime.time(0, 0)), datetime.datetime.combine(next_day, end_t)))
    else:
        windows.append((shift_start, shift_end))

    query_start = min(w[0] for w in windows)
    query_end = max(w[1] for w in windows)
    # Inclui paradas iniciadas antes do início do turno; busca desde 00:00 do dia anterior para capturar paradas em andamento.
    prev_midnight = datetime.datetime.combine(shift_day - datetime.timedelta(days=1), datetime.time.min)
    query_lower_bound = min(query_start, prev_midnight)

    shift_name = shift_row['shift_name'] or 'TURNO'
    api_db = get_api_db()
    if clear_existing:
        # Limpa tanto o dia base quanto o dia seguinte, caso o turno cruze a meia-noite.
        days_to_clear = {shift_day}
        if end_t <= start_t:
            days_to_clear.add(shift_day + datetime.timedelta(days=1))
        for day in days_to_clear:
            api_db.execute('DELETE FROM api WHERE data = ? AND turno = ?', (day.isoformat(), shift_name))

    status_rows = db.execute(
        '''SELECT st.*, st.id AS status_id, l.number AS loom_number, r.code AS reason_code, r.description AS reason_desc
           FROM status_tear st
           JOIN looms l ON l.id = st.loom_id
           LEFT JOIN reasons r ON r.id = st.reason_id
             WHERE st.stop_time IS NOT NULL
               AND st.stop_time >= ?
               AND st.stop_time < ?
               AND (st.start_time IS NULL OR st.start_time > ?)
             ORDER BY st.stop_time''',
        (query_lower_bound.isoformat(), query_end.isoformat(), query_start.isoformat()),
    ).fetchall()

    inserted = 0
    now_dt = now_local()
    now_dt_naive = now_dt.replace(tzinfo=None) if now_dt.tzinfo else now_dt
    limit_future = shift_day >= now_dt_naive.date()

    for row in status_rows:
        stop_dt = parse_iso_naive(row['stop_time'])
        if not stop_dt:
            continue
        start_dt = parse_iso_naive(row['start_time'])
        intervals = []
        for win_start, win_end in windows:
            interval_end = start_dt if start_dt and start_dt < win_end else win_end
            interval_start = max(stop_dt, win_start)
            if interval_end > interval_start and stop_dt < win_end and interval_end > win_start:
                intervals.append((interval_start, interval_end))
        if not intervals:
            continue
        for interval_start, interval_end in intervals:
            if limit_future:
                # Não envia intervalos no futuro; corta no horário atual.
                if now_dt_naive < interval_start:
                    continue
                interval_end = min(interval_end, now_dt_naive)
                if interval_end <= interval_start:
                    continue
            record_date_iso = interval_start.date().isoformat()
            exists_cols = api_db.execute(
                '''SELECT 1 FROM api
                   WHERE data = ? AND turno = ? AND tear = ? AND hora_inicio = ? AND hora_fim = ?
                     AND cod_motivo = ? AND motivo = ? AND responsavel = ?''',
                (
                    record_date_iso,
                    shift_name,
                    row['loom_number'],
                    interval_start.strftime('%H:%M'),
                    interval_end.strftime('%H:%M'),
                    row['reason_code'],
                    row['reason_desc'] or '',
                    row['user_name'] or '',
                ),
            ).fetchone()
            if exists_cols:
                continue
            api_db.execute(
                '''INSERT INTO api (tear, hora_inicio, hora_fim, data, cod_motivo, motivo, turno, responsavel, status_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (
                    row['loom_number'],
                    interval_start.strftime('%H:%M'),
                    interval_end.strftime('%H:%M'),
                    record_date_iso,
                    row['reason_code'],
                    row['reason_desc'] or '',
                    shift_name,
                    row['user_name'] or '',
                    row['status_id'],
                ),
            )
            inserted += 1
    api_db.commit()
    return inserted


@app.route('/admin/export-api', methods=['POST'])
@login_required
@level_required([6])
def export_api_manual():
    shift_id_raw = request.form.get('shift_id')
    date_raw = request.form.get('date') or None
    if not shift_id_raw:
        flash('Informe o turno (shift_id).', 'warning')
        return redirect(url_for('dashboard'))
    try:
        shift_id_int = int(shift_id_raw)
    except Exception:
        flash('shift_id inv?lido.', 'danger')
        return redirect(url_for('dashboard'))
    for_date = None
    if date_raw:
        try:
            for_date = datetime.date.fromisoformat(date_raw)
        except Exception:
            flash('Data inv?lida. Use o formato YYYY-MM-DD.', 'danger')
            return redirect(url_for('dashboard'))
    inserted = export_api_for_shift(shift_id_int, for_date, clear_existing=True)
    if inserted == 0:
        flash('Nenhum registro exportado para api.', 'info')
    else:
        flash(f'{inserted} registro(s) exportados para api.', 'success')
    return redirect(url_for('dashboard'))


@app.route('/enviar-banco', methods=['GET', 'POST'])
@login_required
def enviar_banco():
    # Controles de permissão por turno.
    level = user_level()
    allowed = {1: level in [1, 5, 6], 2: level in [2, 5, 6], 3: level in [3, 5, 6]}

    # Data selecionada
    today = now_local().date()
    selected_date_str = request.args.get('date') or request.form.get('date') or today.isoformat()
    try:
        selected_date = datetime.date.fromisoformat(selected_date_str)
    except Exception:
        selected_date = today
        selected_date_str = today.isoformat()

    if request.method == 'POST':
        turno_idx_raw = request.form.get('turno_index')
        if not turno_idx_raw:
            flash('Selecione o turno para enviar.', 'warning')
            return redirect(url_for('enviar_banco'))
        try:
            turno_idx = int(turno_idx_raw)
        except Exception:
            flash('Turno inválido.', 'danger')
            return redirect(url_for('enviar_banco'))
        if turno_idx not in (1, 2, 3) or not allowed.get(turno_idx, False):
            flash('Você não tem permissão para este turno.', 'danger')
            return redirect(url_for('enviar_banco'))

        db = get_db()
        shift_type = db.execute('SELECT id, name FROM shift_types ORDER BY id LIMIT 1 OFFSET ?', (turno_idx - 1,)).fetchone()
        if not shift_type:
            flash('Tipo de turno não encontrado.', 'danger')
            return redirect(url_for('enviar_banco'))
        weekday_db = (selected_date.weekday() + 1) % 7
        shift_row = db.execute(
            'SELECT id FROM shifts WHERE shift_type_id = ? AND day = ? ORDER BY id LIMIT 1', (shift_type['id'], weekday_db)
        ).fetchone()
        if not shift_row:
            flash('Turno não cadastrado para o dia selecionado.', 'warning')
            return redirect(url_for('enviar_banco'))

        api_db = get_api_db()
        turno_name = shift_type['name'] or 'TURNO'
        already_sent_count = api_db.execute(
            'SELECT COUNT(*) FROM api WHERE data = ? AND turno = ?',
            (selected_date.isoformat(), turno_name),
        ).fetchone()[0]

        day_start = datetime.datetime.combine(selected_date, datetime.time.min)
        day_end = day_start + datetime.timedelta(days=1)
        source_count = db.execute(
            '''SELECT COUNT(*) FROM status_tear st
               JOIN looms l ON l.id = st.loom_id
               LEFT JOIN reasons r ON r.id = st.reason_id
               WHERE st.stop_time IS NOT NULL
                 AND st.stop_time >= ?
                 AND st.stop_time < ?''',
            (day_start.isoformat(), day_end.isoformat()),
        ).fetchone()[0]

        inserted = export_api_for_shift(shift_row['id'], selected_date, clear_existing=False)
        if inserted == 0:
            msg = 'Nenhum registro novo para este turno/data.'
            if already_sent_count and source_count > already_sent_count:
                msg = 'Nenhum registro novo (já enviado anteriormente).'
            flash(msg, 'info')
        else:
            flash(f'{inserted} novo(s) registro(s) exportados para api.', 'success')
        return redirect(url_for('enviar_banco', date=selected_date_str))

    # rota antiga redireciona para a nova página do 1º turno
    return redirect(url_for('enviar_banco_turno1'))


@app.route('/enviar-banco-turno1', methods=['GET', 'POST'])
@login_required
def enviar_banco_turno1():
    level = user_level()
    if level not in [1, 5, 6]:
        flash('Sem permissão para este turno.', 'danger')
        return redirect(url_for('dashboard'))

    today = now_local().date()
    selected_date_str = request.args.get('date') or request.form.get('date') or today.isoformat()
    try:
        selected_date = datetime.date.fromisoformat(selected_date_str)
    except Exception:
        selected_date = today
        selected_date_str = today.isoformat()

    db = get_db()
    shift_type = db.execute('SELECT id, name FROM shift_types ORDER BY id LIMIT 1').fetchone()
    if not shift_type:
        flash('Tipo de turno não configurado.', 'warning')
        return redirect(url_for('dashboard'))
    weekday_db = (selected_date.weekday() + 1) % 7
    shift_row = db.execute(
        'SELECT id, start_1, end_1 FROM shifts WHERE shift_type_id = ? AND day = ? ORDER BY id LIMIT 1',
        (shift_type['id'], weekday_db),
    ).fetchone()
    if not shift_row:
        flash('Turno não cadastrado para a data selecionada.', 'warning')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        inserted = export_api_for_shift(shift_row['id'], selected_date, clear_existing=False)
        if inserted == 0:
            flash('Nenhum registro novo para o 1º turno.', 'info')
        else:
            flash(f'{inserted} novo(s) registro(s) exportados para api.', 'success')
        return redirect(url_for('enviar_banco_turno1', date=selected_date_str))

    api_db = get_api_db()
    params = [selected_date_str, shift_type['name']]
    where_clause = 'data = ? AND turno = ?'
    # Se o turno cruza a meia-noite, traz também registros gravados no dia seguinte.
    if datetime.datetime.strptime(shift_row['start_1'], '%H:%M').time() >= datetime.datetime.strptime(shift_row['end_1'], '%H:%M').time():
        next_day = (selected_date + datetime.timedelta(days=1)).isoformat()
        where_clause = '(data = ? OR data = ?) AND turno = ?'
        params = [selected_date_str, next_day, shift_type['name']]

    rows = api_db.execute(
        f'''SELECT id_api, tear, hora_inicio, hora_fim, data, cod_motivo, motivo, turno, responsavel
           FROM api
           WHERE {where_clause}
           ORDER BY data, id_api''',
        params,
    ).fetchall()

    today_iso = now_local().date().isoformat()
    return render_template(
        'enviar_banco_turno1.html',
        selected_date=selected_date_str,
        today_iso=today_iso,
        api_rows=rows,
    )


@app.route('/enviar-banco-turno3', methods=['GET', 'POST'])
@login_required
def enviar_banco_turno3():
    level = user_level()
    if level not in [3, 5, 6]:
        flash('Sem permissão para este turno.', 'danger')
        return redirect(url_for('dashboard'))

    today = now_local().date()
    selected_date_str = request.args.get('date') or request.form.get('date') or today.isoformat()
    try:
        selected_date = datetime.date.fromisoformat(selected_date_str)
    except Exception:
        selected_date = today
        selected_date_str = today.isoformat()

    db = get_db()
    shift_type = db.execute('SELECT id, name FROM shift_types ORDER BY id LIMIT 1 OFFSET 2').fetchone()
    if not shift_type:
        flash('Tipo de turno não configurado.', 'warning')
        return redirect(url_for('dashboard'))
    weekday_db = (selected_date.weekday() + 1) % 7
    shift_row = db.execute(
        'SELECT id, start_1, end_1 FROM shifts WHERE shift_type_id = ? AND day = ? ORDER BY id LIMIT 1',
        (shift_type['id'], weekday_db),
    ).fetchone()
    if not shift_row:
        flash('Turno não cadastrado para a data selecionada.', 'warning')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        inserted = export_api_for_shift(shift_row['id'], selected_date, clear_existing=False)
        if inserted == 0:
            flash('Nenhum registro novo para o 3º turno.', 'info')
        else:
            flash(f'{inserted} novo(s) registro(s) exportados para api.', 'success')
        return redirect(url_for('enviar_banco_turno3', date=selected_date_str))

    api_db = get_api_db()
    params = [selected_date_str, shift_type['name']]
    where_clause = 'data = ? AND turno = ?'
    if datetime.datetime.strptime(shift_row['start_1'], '%H:%M').time() >= datetime.datetime.strptime(shift_row['end_1'], '%H:%M').time():
        next_day = (selected_date + datetime.timedelta(days=1)).isoformat()
        where_clause = '(data = ? OR data = ?) AND turno = ?'
        params = [selected_date_str, next_day, shift_type['name']]
    rows = api_db.execute(
        f'''SELECT id_api, tear, hora_inicio, hora_fim, data, cod_motivo, motivo, turno, responsavel
           FROM api
           WHERE {where_clause}
           ORDER BY data, id_api''',
        params,
    ).fetchall()

    today_iso = now_local().date().isoformat()
    return render_template(
        'enviar_banco_turno3.html',
        selected_date=selected_date_str,
        today_iso=today_iso,
        api_rows=rows,
    )
@app.route('/enviar-banco-turno2', methods=['GET', 'POST'])
@login_required
def enviar_banco_turno2():
    level = user_level()
    if level not in [2, 5, 6]:
        flash('Sem permissão para este turno.', 'danger')
        return redirect(url_for('dashboard'))

    today = now_local().date()
    selected_date_str = request.args.get('date') or request.form.get('date') or today.isoformat()
    try:
        selected_date = datetime.date.fromisoformat(selected_date_str)
    except Exception:
        selected_date = today
        selected_date_str = today.isoformat()

    db = get_db()
    shift_type = db.execute('SELECT id, name FROM shift_types ORDER BY id LIMIT 1 OFFSET 1').fetchone()
    if not shift_type:
        flash('Tipo de turno não configurado.', 'warning')
        return redirect(url_for('dashboard'))
    weekday_db = (selected_date.weekday() + 1) % 7
    shift_row = db.execute(
        'SELECT id, start_1, end_1 FROM shifts WHERE shift_type_id = ? AND day = ? ORDER BY id LIMIT 1',
        (shift_type['id'], weekday_db),
    ).fetchone()
    if not shift_row:
        flash('Turno não cadastrado para a data selecionada.', 'warning')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        inserted = export_api_for_shift(shift_row['id'], selected_date, clear_existing=False)
        if inserted == 0:
            flash('Nenhum registro novo para o 2º turno.', 'info')
        else:
            flash(f'{inserted} novo(s) registro(s) exportados para api.', 'success')
        return redirect(url_for('enviar_banco_turno2', date=selected_date_str))

    api_db = get_api_db()
    rows = api_db.execute(
        '''SELECT id_api, tear, hora_inicio, hora_fim, data, cod_motivo, motivo, turno, responsavel
           FROM api
           WHERE data = ? AND turno = ?
           ORDER BY id_api''',
        (selected_date_str, shift_type['name']),
    ).fetchall()

    today_iso = now_local().date().isoformat()
    return render_template(
        'enviar_banco_turno2.html',
        selected_date=selected_date_str,
        today_iso=today_iso,
        api_rows=rows,
    )
    rows = api_db.execute(
        '''SELECT id_api, tear, hora_inicio, hora_fim, data, cod_motivo, motivo, turno, responsavel
           FROM api
           WHERE data = ?
           ORDER BY id_api''',
        (selected_date_str,),
    ).fetchall()

    return render_template('enviar_banco.html', selected_date=selected_date_str, allowed=allowed, api_rows=rows)


@app.route('/looms/<int:loom_id>/stop', methods=['POST'])
@login_required
@level_required([1, 2, 3, 6])
def looms_stop(loom_id):
    db = get_db()
    reasons = db.execute('SELECT id FROM reasons').fetchall()
    if not reasons:
        flash('Cadastre motivos antes de parar um tear.', 'danger')
        return redirect(url_for('dashboard_teares'))
    reason_id = request.form.get('reason_id')
    time_str = request.form.get('event_time')
    shift_id_raw = request.form.get('shift_id') or None
    user_row = (
        db.execute('SELECT shift_id, username FROM users WHERE id = ?', (session.get('user_id'),)).fetchone()
        if 'user_id' in session
        else None
    )
    user_shift_id = user_row['shift_id'] if user_row else None
    is_admin = session.get('username') == 'admin'
    has_full_access = is_admin or user_shift_id == 4
    def render_error(msg):
        ctx = build_dashboard_teares_context()
        ctx.update({
            'error_stop': msg,
            'open_modal': 'stop',
            'stop_data': {
                'loom_id': loom_id,
                'event_time': time_str,
                'reason_id': reason_id,
                'shift_id': shift_id_raw,
                'shift_label': get_shift_label(int(shift_id_raw), db) if shift_id_raw else None,
            },
        })
        return render_template('dashboard_teares.html', **ctx)
    if not reason_id or not time_str:
        return render_error('Preencha motivo e horário.')
    if not has_full_access and not shift_id_raw:
        return render_error('Selecione um turno.')
    if shift_id_raw and not has_full_access and not validate_shift_time(int(shift_id_raw), time_str, db):
        return render_error('Horário fora do turno permitido.')
    last_status = db.execute(
        'SELECT * FROM status_tear WHERE loom_id = ? ORDER BY id DESC LIMIT 1', (loom_id,)
    ).fetchone()
    now_date = now_local().date()
    event_dt = datetime.datetime.combine(now_date, datetime.datetime.strptime(time_str, '%H:%M').time())
    if last_status and last_status['start_time']:
        try:
            start_dt_raw = datetime.datetime.fromisoformat(last_status['start_time'])
            start_dt = start_dt_raw.replace(tzinfo=None) if start_dt_raw.tzinfo else start_dt_raw
            if event_dt.date() == start_dt.date() and event_dt < start_dt:
                return render_error('Horário não pode ser anterior ao horário em que o tear foi ligado.')
        except Exception:
            pass
    db.execute(
        '''INSERT INTO status_tear (loom_id, reason_id, status, stop_time, start_time, user_id, user_name)
           VALUES (?, ?, 0, ?, NULL, ?, ?)''',
        (loom_id, int(reason_id), event_dt.isoformat(), session['user_id'], session.get('username', '')),
    )
    db.commit()
    flash('Tear parado.', 'info')
    return redirect(url_for('dashboard_teares'))


@app.route('/looms/<int:loom_id>/start', methods=['POST'])
@login_required
@level_required([1, 2, 3, 6])
def looms_start(loom_id):
    db = get_db()
    time_str = request.form.get('event_time')
    shift_id = request.form.get('shift_id') or None
    reason_id = request.form.get('reason_id') or None
    user_row = (
        db.execute('SELECT shift_id, username FROM users WHERE id = ?', (session.get('user_id'),)).fetchone()
        if 'user_id' in session
        else None
    )
    user_shift_id = user_row['shift_id'] if user_row else None
    is_admin = session.get('username') == 'admin'
    has_full_access = is_admin or user_shift_id == 4
    def render_error(msg):
        ctx = build_dashboard_teares_context()
        ctx.update({
            'error_start': msg,
            'open_modal': 'start',
            'start_data': {
                'loom_id': loom_id,
                'event_time': time_str,
                'shift_id': shift_id,
                'reason_id': reason_id,
                'shift_label': get_shift_label(int(shift_id), db) if shift_id else None,
            },
        })
        return render_template('dashboard_teares.html', **ctx)
    if not time_str:
        return render_error('Preencha horário.')
    if not has_full_access and not shift_id:
        return render_error('Selecione um turno.')
    if shift_id and not has_full_access and not validate_shift_time(int(shift_id), time_str, db):
        return render_error('Horário fora do turno permitido.')
    last = db.execute(
        'SELECT * FROM status_tear WHERE loom_id = ? ORDER BY id DESC LIMIT 1', (loom_id,)
    ).fetchone()
    if not last or last['status'] != 0:
        flash('O tear n?o est? parado.', 'warning')
        return redirect(url_for('dashboard_teares'))
    now_date = now_local().date()
    event_dt = datetime.datetime.combine(now_date, datetime.datetime.strptime(time_str, '%H:%M').time())
    db.execute(
        'UPDATE status_tear SET status = 1, start_time = ?, user_id = ?, user_name = ?, reason_id = COALESCE(reason_id, ?) WHERE id = ?',
        (event_dt.isoformat(), session['user_id'], session.get('username', ''), reason_id, last['id']),
    )
    db.commit()
    flash('Tear iniciado.', 'success')
    return redirect(url_for('dashboard_teares'))


@app.route('/looms')
@login_required
@level_required([5, 6])
def looms_list():
    db = get_db()
    looms = db.execute('''
        SELECT l.id, l.name, l.number
        FROM looms l
        ORDER BY l.number
    ''').fetchall()
    return render_template('looms.html', looms=looms)


@app.route('/looms/new', methods=['GET', 'POST'])
@login_required
@level_required([5, 6])
def looms_create():
    db = get_db()
    if request.method == 'POST':
        name = 'TEAR'
        number = request.form.get('number')
        if not number:
            flash('Número do tear é obrigatório.', 'danger')
        else:
            try:
                db.execute('INSERT INTO looms (name, number) VALUES (?, ?)', (name, number))
                db.commit()
                flash('Tear criado.', 'success')
                return redirect(url_for('looms_list'))
            except sqlite3.IntegrityError:
                flash('Número do tear já existe.', 'danger')
    return render_template('loom_form.html', action_url=url_for('looms_create'), loom=None)


@app.route('/looms/<int:loom_id>/edit', methods=['GET', 'POST'])
@login_required
@level_required([5, 6])
def looms_edit(loom_id):
    db = get_db()
    loom = db.execute('SELECT * FROM looms WHERE id = ?', (loom_id,)).fetchone()
    if not loom:
        flash('Tear não encontrado.', 'danger')
        return redirect(url_for('looms_list'))

    if request.method == 'POST':
        name = 'TEAR'
        number = request.form.get('number')
        if not number:
            flash('Número do tear é obrigatório.', 'danger')
        else:
            try:
                db.execute('UPDATE looms SET name = ?, number = ? WHERE id = ?', (name, number, loom_id))
                db.commit()
                flash('Tear atualizado.', 'success')
                return redirect(url_for('looms_list'))
            except sqlite3.IntegrityError:
                flash('Número do tear já existe.', 'danger')
    return render_template('loom_form.html', action_url=url_for('looms_edit', loom_id=loom_id), loom=loom)


@app.route('/looms/<int:loom_id>/delete', methods=['POST'])
@login_required
@level_required([5, 6])
def looms_delete(loom_id):
    db = get_db()
    db.execute('DELETE FROM looms WHERE id = ?', (loom_id,))
    db.commit()
    flash('Tear removido.', 'info')
    return redirect(url_for('looms_list'))


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--init-db':
        init_db()
        print('Banco inicializado em', DATABASE)
        sys.exit(0)

    if not os.path.exists(DATABASE):
        init_db()
        print('Banco criado automaticamente.')

    app.run(debug=True)

