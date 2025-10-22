# server/app.py
from typing import List
from datetime import datetime, timedelta

from fastapi import FastAPI, HTTPException, Depends, Request, Query
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware

import storage
from domain import (
    # modelos
    StatusAtual, NovoRegistro, Motivo, Tear, Turno,
    Usuario, NovoUsuario, AtualizaUsuario, LoginPayload,
    # regras de negócio
    listar_eventos,
    registrar_parada, registrar_funcionando,
    status_atual_por_tear, status_atual_dos_teares,
    listar_motivos, upsert_motivo, delete_motivo,
    listar_teares, criar_tear, renomear_tear, excluir_tear,
    upsert_turno, delete_turno,
    # auth
    login, user_by_token, autoriza,
)

app = FastAPI(title="Paradas API (isolado)")

# ---------------- CORS ----------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # pode restringir depois
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# -------- Helpers de turno/role --------
TOL_MIN = 10  # tolerância de 10 minutos após a virada do turno

def _at_time(base: datetime, hhmm: str) -> datetime:
    h, m = map(int, hhmm.split(":"))
    return base.replace(hour=h, minute=m, second=0, microsecond=0)

def turno_efetivo(dt: datetime) -> int:
    """
    Retorna 1, 2 ou 3 conforme o horário informado, com tolerância de 10 min na virada,
    idêntico à regra aplicada no front.
    Turnos:
      1: 05:00–13:30
      2: 13:30–22:00
      3: 22:00–05:00 (+1 dia)
    """
    base = dt
    t1_start = _at_time(base, "05:00")
    t2_start = _at_time(base, "13:30")
    t3_start = _at_time(base, "22:00")
    next_day_5 = _at_time(base, "05:00") + timedelta(days=1)

    t1_tol = t1_start + timedelta(minutes=TOL_MIN)
    t2_tol = t2_start + timedelta(minutes=TOL_MIN)
    t3_tol = t3_start + timedelta(minutes=TOL_MIN)

    if dt >= t1_start and dt < t2_start:
        return 3 if dt < t1_tol else 1
    if dt >= t2_start and dt < t3_start:
        return 1 if dt < t2_tol else 2
    # 22:00 -> 05:00(+1)
    if dt >= t3_start or dt < t1_start:
        if dt >= t3_start and dt < t3_tol:
            return 2
        return 3
    return 1

def valida_registro_por_role_e_turno(user_role: int, data_hora_iso: str):
    """
    Lança HTTPException se a combinação role/horário violar as regras.
    """
    try:
        sel = datetime.fromisoformat(data_hora_iso.replace("Z", "+00:00")).astimezone().replace(tzinfo=None)
    except Exception:
        raise HTTPException(status_code=400, detail="data_hora inválido (use ISO-8601).")

    agora = datetime.now()

    # Bloqueio universal de FUTURO (inclusive para role 6)
    if sel > agora:
        raise HTTPException(status_code=400, detail="Não é permitido registrar no futuro.")

    # Roles 4 e 5 nunca podem
    if user_role in (4, 5):
        raise HTTPException(status_code=403, detail="Seu perfil não está autorizado a registrar paradas/funcionamento.")

    # Role 6 (TI) pode qualquer horário passado (sem exigir turno atual)
    if user_role == 6:
        return

    # Para roles 1/2/3: precisa estar no turno atual e casar turno==role
    turno_sel = turno_efetivo(sel)
    turno_agora = turno_efetivo(agora)

    if turno_sel != turno_agora:
        raise HTTPException(status_code=400, detail="Horário informado pertence a outro turno (fora da tolerância de 10 minutos).")

    if user_role in (1, 2, 3) and turno_sel != user_role:
        raise HTTPException(status_code=403, detail=f"Seu perfil só pode registrar no {user_role}º turno.")


# -------- AUTH HELPERS (antes das rotas) --------
def get_user_from_auth(request: Request):
    bearer = request.headers.get("Authorization", "")
    if bearer.startswith("Bearer "):
        token = bearer[7:]
        u = user_by_token(token)
        if u:
            return u
    return None

def require(recurso: str):
    def dep(user=Depends(get_user_from_auth)):
        if not user:
            raise HTTPException(status_code=401, detail="Não autenticado")
        if not autoriza(int(user["role"]), recurso):
            raise HTTPException(status_code=403, detail="Sem permissão")
        return user
    return dep

# Novo: aceita qualquer um dos recursos informados (OR)
def require_any(*recursos: str):
    def dep(user=Depends(get_user_from_auth)):
        if not user:
            raise HTTPException(status_code=401, detail="Não autenticado")
        role = int(user["role"])
        if not any(autoriza(role, r) for r in recursos):
            raise HTTPException(status_code=403, detail="Sem permissão")
        return user
    return dep


# ---------------- ROTAS ----------------

# ---- Dashboard / Status ----
@app.get("/status", response_model=List[StatusAtual])
def get_status(total: int = Query(50, ge=1, le=500), user=Depends(require("dashboard"))):
    # legado: calcula status para 1..N
    return status_atual_por_tear(total)

@app.get("/status-teares", response_model=List[StatusAtual])
def get_status_teares(user=Depends(require("dashboard"))):
    # novo: usa teares cadastrados
    return status_atual_dos_teares()

# Observação: eventos é usado pelos relatórios -> liberar leitura via api_read
@app.get("/eventos")
def eventos(user=Depends(require_any("dashboard", "api_read"))):
    return jsonable_encoder([e for e in listar_eventos()])

@app.post("/parada")
def post_parada(payload: NovoRegistro, user=Depends(require("dashboard"))):
    # >>> Regras de role/turno <<<
    valida_registro_por_role_e_turno(int(user["role"]), payload.data_hora)
    try:
        ev = registrar_parada(payload)
        return ev.model_dump()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/funcionando")
def post_funcionando(payload: NovoRegistro, user=Depends(require("dashboard"))):
    # >>> Regras de role/turno <<<
    valida_registro_por_role_e_turno(int(user["role"]), payload.data_hora)
    try:
        ev = registrar_funcionando(payload)
        return ev.model_dump()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---- Motivos ----
# GET liberado com api_read; mutações continuam exigindo 'motivos'
@app.get("/motivos")
def motivos(user=Depends(require_any("motivos", "api_read"))):
    return listar_motivos()

@app.post("/motivos", response_model=Motivo)
def post_motivo(m: Motivo, user=Depends(require("motivos"))):
    return upsert_motivo(m)

@app.delete("/motivos/{codigo}")
def del_motivo(codigo: int, user=Depends(require("motivos"))):
    return delete_motivo(codigo)


# ---- Teares ----
# GET liberado com api_read; mutações exigem 'teares'
@app.get("/teares")
def get_teares(user=Depends(require_any("teares", "api_read"))):
    return listar_teares()

@app.post("/teares", response_model=Tear)
def post_teares(nome: str | None = None, user=Depends(require("teares"))):
    return criar_tear(nome)

@app.put("/teares/{codigo}", response_model=Tear)
def put_teares(codigo: int, novo_nome: str, user=Depends(require("teares"))):
    try:
        return renomear_tear(codigo, novo_nome)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.delete("/teares/{codigo}")
def delete_teares(codigo: int, user=Depends(require("teares"))):
    return excluir_tear(codigo)


# ---- Turnos ----
# GET liberado com api_read; mutações exigem 'turnos'
@app.get("/turnos")
def turnos(user=Depends(require_any("turnos", "api_read"))):
    return storage.read("turnos")

@app.post("/turnos")
def post_turno(t: Turno, user=Depends(require("turnos"))):
    return upsert_turno(t)

@app.delete("/turnos/{dia_semana}/{turno}")
def del_turno(dia_semana: int, turno: int, user=Depends(require("turnos"))):
    return delete_turno(dia_semana, turno)


# ---- Login / sessão ----
@app.post("/login")
def do_login(payload: LoginPayload):
    try:
        return login(payload.nome, payload.senha)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/me")
def me(user=Depends(get_user_from_auth)):
    if not user:
        raise HTTPException(status_code=401, detail="Não autenticado")
    return user


# ---- Usuários (CRUD) - apenas TI ----
@app.get("/usuarios")
def get_users(user=Depends(require("usuarios"))):
    from domain import listar_usuarios
    return listar_usuarios()

@app.post("/usuarios")
def post_user(nu: NovoUsuario, user=Depends(require("usuarios"))):
    try:
        from domain import criar_usuario
        return criar_usuario(nu)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.put("/usuarios/{cod}")
def put_user(cod: int, up: AtualizaUsuario, user=Depends(require("usuarios"))):
    try:
        from domain import atualizar_usuario
        return atualizar_usuario(cod, up)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/usuarios/{cod}")
def del_user(cod: int, user=Depends(require("usuarios"))):
    try:
        from domain import excluir_usuario
        return excluir_usuario(cod)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/health")
def health():
    return {"ok": True}

# ---- Main ----
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
