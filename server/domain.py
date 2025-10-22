import secrets, hashlib, hmac
from typing import Optional, List, Dict, Any, Tuple
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, time, timedelta
from dateutil import tz
import storage
from dateutil import tz
TZ = tz.gettz("America/Sao_Paulo")

def to_local(dt):
    if dt.tzinfo is None: return dt.replace(tzinfo=TZ)
    return dt.astimezone(TZ)

class Evento(BaseModel):
    tear: int = Field(..., ge=1)
    data_hora: datetime
    status: int = Field(..., ge=0, le=1)  # 1=funcionando, 0=parado
    hora_registro: datetime
    motivo: Optional[int] = None
    turno: Optional[int] = None

class NovoRegistro(BaseModel):
    tear: int
    data_hora: datetime
    motivo: Optional[int] = None  # só para parada

class Motivo(BaseModel):
    codigo: int
    descricao: str

class StatusAtual(BaseModel):
    tear: int
    status: int
    desde: Optional[datetime] = None
    horas: Optional[float] = None
    nome: Optional[str] = None  # <- novo

class Turno(BaseModel):
    turno: int = Field(..., ge=1, le=3)       # 1,2,3 (ajuste se usar mais)
    dia_semana: int = Field(..., ge=1, le=7)  # 1=segunda ... 7=domingo
    inicio: str  # "HH:MM"
    fim: str     # "HH:MM"

class Tear(BaseModel):
    codigo: int
    nome: str

# ======= USUÁRIOS / ROLES (ATUALIZADO 1..6) =======
# 1 = Líder 1º turno
# 2 = Líder 2º turno
# 3 = Líder 3º turno
# 4 = Processos
# 5 = Gestor
# 6 = TI
class Usuario(BaseModel):
    cod: int
    nome: str
    senha_hash: str
    role: int = Field(..., ge=1, le=6)  # <- antes le=4

class NovoUsuario(BaseModel):
    nome: str
    senha: str
    role: int = Field(..., ge=1, le=6)  # <- antes le=4

class AtualizaUsuario(BaseModel):
    nome: Optional[str] = None
    senha: Optional[str] = None
    role: Optional[int] = Field(None, ge=1, le=6)  # <- antes le=4

class LoginPayload(BaseModel):
    nome: str
    senha: str


def _parse_hhmm(hhmm: str) -> time:
    h, m = map(int, hhmm.split(':'))
    return time(hour=h, minute=m)

def turno_atual(dt: datetime) -> int:
    """Retorna o número do turno vigente no instante dt (timezone local)."""
    d = dt.isoweekday()  # 1..7
    turnos = storage.read('turnos')

    ttime = dt.time()
    for t in turnos:
        if t['dia_semana'] != d:
            continue
        ini = _parse_hhmm(t['inicio'])
        fim = _parse_hhmm(t['fim'])

        if ini < fim:
            # janela normal (ex.: 05:00-14:00)
            if ini <= ttime < fim:
                return int(t['turno'])
        else:
            # cruza meia-noite (ex.: 22:00-05:00) → vale se (>= ini) OU (< fim)
            if (ttime >= ini) or (ttime < fim):
                return int(t['turno'])

    # fallback se nada casar
    return 1

def _dt_replace(d: datetime, t: time) -> datetime:
    return d.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)

def janela_turno_vigente(agora: datetime) -> tuple[datetime, datetime, int]:
    """
    Retorna (inicio, fim, turno_num) da janela do turno EM QUE O USUÁRIO ESTÁ AGORA.
    Para turnos que cruzam a meia-noite (ex.: 22:00→05:00), 'fim' é no dia seguinte.
    """
    d = agora.isoweekday()          # 1..7
    ttime = agora.time()
    turnos = storage.read('turnos')

    for t in turnos:
        if t['dia_semana'] != d:
            continue
        ini = _parse_hhmm(t['inicio'])
        fim = _parse_hhmm(t['fim'])

        if ini < fim:
            # janela normal no mesmo dia
            dt_ini = _dt_replace(agora, ini)
            dt_fim = _dt_replace(agora, fim)
            if dt_ini <= agora < dt_fim:
                return dt_ini, dt_fim, int(t['turno'])
        else:
            # cruza meia-noite: [ini, 24h) U [00:00, fim)
            if ttime >= ini:
                dt_ini = _dt_replace(agora, ini)                 # hoje às 22:00
                dt_fim = _dt_replace(agora + timedelta(days=1), fim)  # amanhã às 05:00
                return dt_ini, dt_fim, int(t['turno'])
            if ttime < fim:
                dt_ini = _dt_replace(agora - timedelta(days=1), ini)  # ontem às 22:00
                dt_fim = _dt_replace(agora, fim)                      # hoje às 05:00
                return dt_ini, dt_fim, int(t['turno'])

    # fallback (não deve acontecer se turnos estiverem configurados)
    dt_ini = agora.replace(hour=5, minute=0, second=0, microsecond=0)
    dt_fim = agora.replace(hour=14, minute=0, second=0, microsecond=0)
    return dt_ini, dt_fim, 1


def inicio_turno_atual(agora: datetime) -> datetime:
    """Retorna o datetime exato do início do turno vigente no instante 'agora'."""
    d = agora.isoweekday()
    turnos = storage.read('turnos')
    ttime = agora.time()

    for t in turnos:
        if t['dia_semana'] != d:
            continue
        ini = _parse_hhmm(t['inicio'])
        fim = _parse_hhmm(t['fim'])

        if ini < fim:
            # janela normal no mesmo dia
            dt_ini = agora.replace(hour=ini.hour, minute=ini.minute, second=0, microsecond=0)
            dt_fim = agora.replace(hour=fim.hour, minute=fim.minute, second=0, microsecond=0)
            if dt_ini <= agora < dt_fim:
                return dt_ini
        else:
            # janela cruza meia-noite: [ini, 24h) U [00:00, fim)
            if ttime >= ini:
                # estamos na parte "hoje >= ini"
                return agora.replace(hour=ini.hour, minute=ini.minute, second=0, microsecond=0)
            if ttime < fim:
                # estamos após meia-noite, turno começou ontem às 'ini'
                ontem = (agora - timedelta(days=1)).replace(
                    hour=ini.hour, minute=ini.minute, second=0, microsecond=0
                )
                return ontem

    # fallback: 05:00 do mesmo dia
    return agora.replace(hour=5, minute=0, second=0, microsecond=0)


def listar_eventos() -> List[Evento]:
    return [Evento(**e) for e in storage.read('status')]

def salvar_evento(ev: Evento):
    data = storage.read('status')
    data.append(jsonable_encoder(ev))  # <- garante serialização (datetime -> ISO)
    storage.write('status', data)


def status_atual_por_tear(total: int) -> List[StatusAtual]:
    eventos = listar_eventos()
    por = {i: [] for i in range(1, total + 1)}
    for e in eventos:
        por.setdefault(e.tear, []).append(e)
    agora = datetime.now(TZ)
    saida: List[StatusAtual] = []
    for tear, lst in por.items():
        lst = sorted(lst, key=lambda x: x.data_hora)
        if not lst:
            saida.append(StatusAtual(tear=tear, status=1, desde=None, horas=None))
            continue
        last = lst[-1]
        desde = last.data_hora
        for prev in reversed(lst[:-1]):
            if prev.status != last.status:
                break
            desde = prev.data_hora
        horas = (agora - desde).total_seconds() / 3600.0 if desde else None
        saida.append(StatusAtual(tear=tear, status=last.status, desde=desde, horas=round(horas, 2) if horas else None))
    return saida

def status_atual_dos_teares() -> List[StatusAtual]:
    teares = storage.read('teares')  # [{codigo, nome}, ...]
    eventos = listar_eventos()
    por: dict[int, List[Evento]] = {}
    for e in eventos:
        por.setdefault(e.tear, []).append(e)
    agora = datetime.now(TZ)
    saida: List[StatusAtual] = []
    for t in sorted(teares, key=lambda x: int(x['codigo'])):
        cod = int(t['codigo'])
        lst = sorted(por.get(cod, []), key=lambda x: x.data_hora)
        if not lst:
            # Sem eventos: assume funcionando
            saida.append(StatusAtual(tear=cod, nome=t.get('nome'), status=1, desde=None, horas=None))
            continue
        last = lst[-1]
        # “desde” do mesmo status
        desde = last.data_hora
        for prev in reversed(lst[:-1]):
            if prev.status != last.status:
                break
            desde = prev.data_hora
        horas = (agora - desde).total_seconds()/3600.0 if desde else None
        saida.append(StatusAtual(
            tear=cod, nome=t.get('nome'), status=last.status,
            desde=desde, horas=round(horas, 2) if horas is not None else None
        ))
    return saida

def registrar_parada(payload: NovoRegistro) -> Evento:
    if not tear_existe(payload.tear):
        raise ValueError('Tear inexistente. Cadastre o tear antes de registrar.')
    agora = datetime.now(TZ)
    local_dt = to_local(payload.data_hora)

    ini, fim, turno_vigente = janela_turno_vigente(agora)
    if not (ini <= local_dt < fim):
        raise ValueError(
            f'Data/Hora fora da janela do turno vigente '
            f'({ini.strftime("%d/%m %H:%M")}–{fim.strftime("%d/%m %H:%M")})'
        )

    ev = Evento(
        tear=payload.tear,
        data_hora=local_dt,
        status=0,
        hora_registro=agora,
        motivo=payload.motivo,
        turno=turno_vigente,
    )
    salvar_evento(ev)
    return ev

def registrar_funcionando(payload: NovoRegistro) -> Evento:
    if not tear_existe(payload.tear):
        raise ValueError('Tear inexistente. Cadastre o tear antes de registrar.')
    agora = datetime.now(TZ)
    local_dt = to_local(payload.data_hora)
    turno_registro = turno_atual(local_dt)
    ev = Evento(
        tear=payload.tear,
        data_hora=local_dt,
        status=1,
        hora_registro=agora,
        motivo=None,
        turno=turno_registro,
    )
    salvar_evento(ev)
    return ev


def upsert_turno(t: Turno) -> Turno:
    rows = storage.read('turnos')
    # substitui se existir mesmo (dia_semana, turno)
    updated = False
    for i, r in enumerate(rows):
        if r['dia_semana'] == t.dia_semana and r['turno'] == t.turno:
            rows[i] = t.model_dump()
            updated = True
            break
    if not updated:
        rows.append(t.model_dump())
    storage.write('turnos', rows)
    return t

def delete_turno(dia_semana: int, turno: int) -> dict:
    rows = storage.read('turnos')
    new = [r for r in rows if not (r['dia_semana'] == dia_semana and r['turno'] == turno)]
    storage.write('turnos', new)
    return {'ok': True}

# --- Motivos de Parada (CRUD simples) ----
def listar_motivos():
    return storage.read('motivos')

def upsert_motivo(m: Motivo) -> Motivo:
    rows = storage.read('motivos')
    for i, r in enumerate(rows):
        if int(r['codigo']) == int(m.codigo):
            rows[i] = m.model_dump()
            storage.write('motivos', rows)
            return m
    rows.append(m.model_dump())
    storage.write('motivos', rows)
    return m

def delete_motivo(codigo: int) -> dict:
    rows = storage.read('motivos')
    rows = [r for r in rows if int(r['codigo']) != int(codigo)]
    storage.write('motivos', rows)
    return {'ok': True}

# ---------- TEARES (máquinas) ----------
def listar_teares() -> list[dict]:
    return storage.read('teares')

def _proximo_codigo(teares: list[dict]) -> int:
    if not teares:
        return 1
    return max(int(t['codigo']) for t in teares) + 1

def _nome_padrao(codigo: int) -> str:
    # pelo menos 2 dígitos: tear01, tear02 ... tear10, tear100 etc.
    return f"tear{codigo:02d}"

def criar_tear(nome: str | None = None) -> Tear:
    teares = storage.read('teares')
    codigo = _proximo_codigo(teares)
    nome_final = nome.strip() if (nome and nome.strip()) else _nome_padrao(codigo)
    novo = Tear(codigo=codigo, nome=nome_final)
    teares.append(novo.model_dump())
    storage.write('teares', teares)
    return novo

def renomear_tear(codigo: int, novo_nome: str) -> Tear:
    teares = storage.read('teares')
    for i, t in enumerate(teares):
        if int(t['codigo']) == int(codigo):
            teares[i]['nome'] = (novo_nome or '').strip() or _nome_padrao(codigo)
            storage.write('teares', teares)
            return Tear(**teares[i])
    raise ValueError('Tear não encontrado')

def excluir_tear(codigo: int) -> dict:
    teares = storage.read('teares')
    novo = [t for t in teares if int(t['codigo']) != int(codigo)]
    storage.write('teares', novo)
    return {'ok': True}

def tear_existe(codigo: int) -> bool:
    teares = storage.read('teares')
    return any(int(t['codigo']) == int(codigo) for t in teares)

_SECRET = "paradas-secret-salt"  # se quiser, mova para .env
def _hash_senha(senha: str) -> str:
    import hashlib
    return hashlib.pbkdf2_hmac('sha256', senha.encode('utf-8'), _SECRET.encode('utf-8'), 100_000).hex()

def _parece_hash(valor: str) -> bool:
    if not isinstance(valor, str) or len(valor) != 64:
        return False
    try:
        int(valor, 16); return True
    except Exception:
        return False

def _verifica_senha(senha: str, senha_hash_armazenado: str) -> bool:
    # Se já é hash, compara com PBKDF2; se for legado (texto puro), compara direto
    if _parece_hash(senha_hash_armazenado):
        import hmac
        calc = _hash_senha(senha)
        return hmac.compare_digest(calc, senha_hash_armazenado)
    else:
        return senha == senha_hash_armazenado

def _bootstrap_admin():
    users = storage.read('users')
    if not users:
        # Admin agora nasce como TI (role 6)
        admin = Usuario(cod=1, nome='admin', senha_hash=_hash_senha('admin'), role=6)
        storage.write('users', [admin.model_dump()])
_bootstrap_admin()

def _prox_cod(users: List[Dict[str, Any]]) -> int:
    return (max([u['cod'] for u in users]) + 1) if users else 1

def listar_usuarios() -> List[Dict[str, Any]]:
    users = storage.read('users')
    # nunca devolve hash
    return [{'cod': u['cod'], 'nome': u['nome'], 'role': u['role'] } for u in users]

def criar_usuario(nu: NovoUsuario) -> Dict[str, Any]:
    users = storage.read('users')
    if any(u['nome'].lower() == nu.nome.lower() for u in users):
        raise ValueError('Nome já existe')
    cod = _prox_cod(users)
    novo = Usuario(cod=cod, nome=nu.nome.strip(), senha_hash=_hash_senha(nu.senha), role=nu.role)
    users.append(novo.model_dump())
    storage.write('users', users)
    return {'cod': cod, 'nome': novo.nome, 'role': novo.role}

def atualizar_usuario(cod: int, up: AtualizaUsuario) -> Dict[str, Any]:
    users = storage.read('users')
    for u in users:
        if int(u['cod']) == int(cod):
            if up.nome is not None: u['nome'] = up.nome.strip()
            if up.senha is not None: u['senha_hash'] = _hash_senha(up.senha)
            if up.role is not None: u['role'] = up.role
            storage.write('users', users)
            return {'cod': u['cod'], 'nome': u['nome'], 'role': u['role']}
    raise ValueError('Usuário não encontrado')

def excluir_usuario(cod: int) -> Dict[str, Any]:
    users = storage.read('users')
    novo = [u for u in users if int(u['cod']) != int(cod)]
    if len(novo) == len(users): raise ValueError('Usuário não encontrado')
    storage.write('users', novo)
    return {'ok': True}

def login(nome: str, senha: str) -> dict:
    users = storage.read('users')
    user = next((u for u in users if u['nome'].lower() == nome.lower()), None)
    if not user or not _verifica_senha(senha, user['senha_hash']):
        raise ValueError('Credenciais inválidas')

    # migração automática de legado -> hash
    if not _parece_hash(user['senha_hash']):
        user['senha_hash'] = _hash_senha(senha)
        storage.write('users', users)

    import secrets
    token = secrets.token_hex(16)
    sessions = storage.read('sessions')
    sessions = [s for s in sessions if s.get('cod') != user['cod']]
    from datetime import datetime
    from dateutil import tz
    TZ = tz.gettz("America/Sao_Paulo")
    sessions.append({'token': token, 'cod': user['cod'], 'created_at': datetime.now(TZ).isoformat()})
    storage.write('sessions', sessions)
    return {'token': token, 'user': {'cod': user['cod'], 'nome': user['nome'], 'role': user['role']}}

def user_by_token(token: str) -> Optional[Dict[str, Any]]:
    sessions = storage.read('sessions')
    sess = next((s for s in sessions if s['token'] == token), None)
    if not sess: return None
    users = storage.read('users')
    return next(({'cod': u['cod'], 'nome': u['nome'], 'role': u['role']} for u in users if u['cod'] == sess['cod']), None)

# ======= PERMISSÕES POR PAPEL (ATUALIZADO 1..6) =======
# recursos: dashboard, turnos, teares, motivos, relatorios, usuarios, api_read, relatorio_turno1
PERMISSOES = {
    1: {'dashboard', 'api_read', 'relatorio_turno1'},            # Líder 1º turno
    2: {'dashboard', 'api_read', 'relatorio_turno2'},                                # Líder 2º turno
    3: {'dashboard', 'api_read', 'relatorio_turno3'},                                # Líder 3º turno
    4: {'dashboard','turnos','teares','motivos','api_read'},     # Processos
    5: {'dashboard','relatorios','api_read'},                    # Gestor
    6: {'dashboard','turnos','teares','motivos','relatorios','usuarios','api_read'}  # TI
}

def autoriza(role: int, recurso: str) -> bool:
    return recurso in PERMISSOES.get(int(role or 0), set())

# helper de conveniência (opcional)
def pode_ler_api(role: int) -> bool:
    return autoriza(role, 'api_read')