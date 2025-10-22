import React, { useEffect, useMemo, useState } from "react";
import { get } from "./api";
import { useNavigate } from "react-router-dom";

/* ====================== Tipos ====================== */
type Modo = "funcionando" | "parado";
type Tear = { codigo: number; nome: string };
type Evento = {
  tear: number;
  data_hora: string; // "YYYY-MM-DD HH:MM:SS" (local)
  status: 0 | 1;
  turno?: 1 | 2 | 3;
  motivo?: number | null;
};
type Turno = {
  dia_semana: number; // 1=Seg ... 7=Dom
  turno: 1 | 2 | 3;
  inicio: string;     // "HH:MM"
  fim: string;        // "HH:MM"
};
type Motivo = { codigo: number; descricao: string };

/* ====================== Helpers ====================== */
const meses = ["jan","fev","mar","abr","mai","jun","jul","ago","set","out","nov","dez"];
const fmtDiaLabel = (d: Date) => `${String(d.getDate()).padStart(2,"0")}/${meses[d.getMonth()]}`;
const startOfDay = (d: Date) => { const x = new Date(d); x.setHours(0,0,0,0); return x; };
const endOfDay   = (d: Date) => { const x = new Date(d); x.setHours(23,59,59,999); return x; };
const addDays    = (d: Date, n: number) => { const x = new Date(d); x.setDate(x.getDate()+n); return x; };
const parseLocalYmd = (ymd: string) => new Date(`${ymd}T00:00:00`);
const sameYMD = (a: Date, b: Date) =>
  a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
const minutesToHours = (m: number) => m / 60;
const weekday1to7 = (d: Date) => (d.getDay() === 0 ? 7 : d.getDay());
const diffMinutes = (a: Date, b: Date) => Math.max(0, Math.round((b.getTime() - a.getTime()) / 60000));
const fmtHM = (hours: number) => {
  const total = Math.max(0, Math.round(hours * 60));
  const h = Math.floor(total/60), m = total % 60;
  return `${h}:${String(m).padStart(2,"0")}`;
};
const asLocalDate = (s: string) => new Date(s.includes("T") ? s : s.replace(" ", "T"));

function clampIntervalToDay(a: Date, b: Date, day: Date) {
  const ds = startOfDay(day), de = endOfDay(day);
  const ini = new Date(Math.max(a.getTime(), ds.getTime()));
  const fim = new Date(Math.min(b.getTime(), de.getTime()));
  if (fim <= ini) return null;
  return { ini, fim };
}

/* ===== soma status==0 (parado) em um intervalo, agrupando por motivo ===== */
function sumParadasByMotivoInInterval(
  events: Evento[],
  tear: number,
  ini: Date,
  fim: Date
): Map<number, number> {
  const regs = events
    .filter(e => e.tear === tear)
    .sort((a,b)=> asLocalDate(a.data_hora).getTime() - asLocalDate(b.data_hora).getTime());
  const out = new Map<number, number>();
  if (regs.length === 0 || ini >= fim) return out;

  // estado e motivo no início
  let estadoIni: 0|1 = 1;
  let motivoIni: number | null | undefined = null;
  for (let k=regs.length-1;k>=0;k--){
    const t = asLocalDate(regs[k].data_hora);
    if (t <= ini) {
      estadoIni = regs[k].status as 0|1;
      motivoIni = regs[k].motivo;
      break;
    }
  }
  const dentro = regs.filter(r => {
    const t = asLocalDate(r.data_hora);
    return t >= ini && t <= fim;
  }).sort((a,b)=> asLocalDate(a.data_hora).getTime() - asLocalDate(b.data_hora).getTime());

  const seq: Array<{t: Date; status: 0|1; motivo?: number|null}> = [
    { t: ini, status: estadoIni, motivo: motivoIni },
    ...dentro.map(e => ({ t: asLocalDate(e.data_hora), status: e.status as 0|1, motivo: e.motivo })),
    { t: new Date(fim.getTime()+1), status: dentro.length ? (dentro[dentro.length-1].status as 0|1) : estadoIni, motivo: dentro.length ? dentro[dentro.length-1].motivo : motivoIni }
  ];

  for (let i=0;i<seq.length-1;i++){
    const cur = seq[i], nxt = seq[i+1];
    if (cur.status !== 0) continue;
    const a = i === 0 ? ini : cur.t;
    const b = (i+1) === seq.length-1 ? fim : nxt.t;
    const mins = diffMinutes(a,b);
    const mot = Number(cur.motivo ?? 0);
    out.set(mot, (out.get(mot) || 0) + mins);
  }
  return out;
}

/* ===== calcula trabalhado/paro por dia (considera turnos e cruzamento 00:00) ===== */
type DayTotals = { worked: number; paradas: number }; // minutos

function computeDayTotalsForTear(
  day: Date,
  tear: number,
  selectedTurnos: Set<string>,
  allTurnos: Turno[],
  events: Evento[],
  nowLocal: Date
): DayTotals {
  const dow = weekday1to7(day);
  const turnosDia = (allTurnos.filter(t => t.dia_semana === dow))
    .filter(t => selectedTurnos.has(String(t.turno)));

  let worked = 0;
  let paradas = 0;

  for (const t of turnosDia) {
    const [hi,mi] = t.inicio.split(":").map(Number);
    const [hf,mf] = t.fim.split(":").map(Number);

    const baseIni = new Date(day); baseIni.setHours(hi||0, mi||0, 0, 0);
    let baseFim  = new Date(day);  baseFim.setHours(hf||0, mf||0, 0, 0);
    const crosses = baseFim <= baseIni;
    if (crosses) baseFim = addDays(baseFim, 1);

    const candidates: Array<{ini: Date; fim: Date}> = [{ ini: baseIni, fim: baseFim }];
    if (crosses) {
      const prevIni = addDays(baseIni, -1);
      const prevFim = new Date(day); prevFim.setHours(hf||0, mf||0, 0, 0);
      candidates.push({ ini: prevIni, fim: prevFim });
    }

    for (const seg of candidates) {
      const clipped = clampIntervalToDay(seg.ini, seg.fim, day);
      if (!clipped) continue;

      let { ini, fim } = clipped;
      if (sameYMD(day, nowLocal) && fim > nowLocal) {
        if (nowLocal <= ini) continue;
        fim = nowLocal;
      }
      const overlap = diffMinutes(ini, fim);
      if (overlap <= 0) continue;

      worked += overlap;
      paradas += Array.from(sumParadasByMotivoInInterval(events, tear, ini, fim).values()).reduce((s,n)=>s+n,0);
    }
  }

  return { worked, paradas };
}

/* ===== paradas por motivo/dia (considera turnos e cruzamento 00:00) ===== */
function computeParadasPorMotivoDia(
  day: Date,
  tear: number,
  selectedTurnos: Set<string>,
  allTurnos: Turno[],
  events: Evento[],
  nowLocal: Date
): Map<number, number> {
  const dow = weekday1to7(day);
  const turnosDia = (allTurnos.filter(t => t.dia_semana === dow))
    .filter(t => selectedTurnos.has(String(t.turno)));

  const acc = new Map<number, number>();

  for (const t of turnosDia) {
    const [hi,mi] = t.inicio.split(":").map(Number);
    const [hf,mf] = t.fim.split(":").map(Number);

    const baseIni = new Date(day); baseIni.setHours(hi||0, mi||0, 0, 0);
    let baseFim  = new Date(day);  baseFim.setHours(hf||0, mf||0, 0, 0);
    const crosses = baseFim <= baseIni;
    if (crosses) baseFim = addDays(baseFim, 1);

    const candidates: Array<{ini: Date; fim: Date}> = [{ ini: baseIni, fim: baseFim }];
    if (crosses) {
      const prevIni = addDays(baseIni, -1);
      const prevFim = new Date(day); prevFim.setHours(hf||0, mf||0, 0, 0);
      candidates.push({ ini: prevIni, fim: prevFim });
    }

    for (const seg of candidates) {
      const clipped = clampIntervalToDay(seg.ini, seg.fim, day);
      if (!clipped) continue;
      let { ini, fim } = clipped;
      if (sameYMD(day, nowLocal) && fim > nowLocal) {
        if (nowLocal <= ini) continue;
        fim = nowLocal;
      }
      if (diffMinutes(ini,fim) <= 0) continue;

      const mp = sumParadasByMotivoInInterval(events, tear, ini, fim);
      for (const [mot, mins] of mp) acc.set(mot, (acc.get(mot) || 0) + mins);
    }
  }

  return acc;
}

/* =============================== Componente =============================== */
export default function RelatorioTurno1() {
  const navigate = useNavigate();

  /* --------- filtros/estados (Tabela superior + Gráfico) --------- */
  const [dtIni, setDtIni] = useState<string>(() => {
    const d = new Date(); d.setDate(d.getDate() - 7);
    return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;
  });
  const [dtFim, setDtFim] = useState<string>(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;
  });
  const [teares, setTeares] = useState<Tear[]>([]);
  const [selTeares, setSelTeares] = useState<Set<number>>(new Set());
  const [modo, setModo] = useState<Modo>("funcionando");

  // <<< FIXO NO 1º TURNO >>>
  const selTurnos = useMemo<Set<string>>(() => new Set(["1"]), []);
  const gTurnos   = useMemo<Set<string>>(() => new Set(["1"]), []);
  const mTurnos   = useMemo<Set<string>>(() => new Set(["1"]), []);

  const [eventos, setEventos] = useState<Evento[]>([]);
  const [turnos, setTurnos] = useState<Turno[]>([]);
  const [motivos, setMotivos] = useState<Motivo[]>([]);

  useEffect(() => {
    (async () => {
      const t: Tear[] = await get("/teares");
      setTeares(t || []);
      setSelTeares(new Set((t || []).map(x => Number(x.codigo))));

      const evts: Evento[] = await get("/eventos");
      evts.sort((a,b)=> a.tear - b.tear || asLocalDate(a.data_hora).getTime() - asLocalDate(b.data_hora).getTime());
      setEventos(evts || []);

      const tr: Turno[] = await get("/turnos");
      setTurnos(tr || []);

      const mv: Motivo[] = await get("/motivos");
      mv.sort((a,b)=> a.codigo - b.codigo);
      setMotivos(mv || []);
    })();
  }, []);

  const dias = useMemo(() => {
    const out: Date[] = [];
    let d = startOfDay(parseLocalYmd(dtIni));
    const fim = startOfDay(parseLocalYmd(dtFim));
    while (d <= fim) { out.push(new Date(d)); d = addDays(d, 1); }
    return out;
  }, [dtIni, dtFim]);

  /* -------- tabela superior (por tear x dia) -------- */
  const { matriz, totalLinha, totalColuna, totalGeral, linhas } = useMemo(() => {
    const linhas = teares
      .filter(t => selTeares.has(Number(t.codigo)))
      .sort((a,b)=>a.codigo - b.codigo);

    const mMins: number[][] = linhas.map(()=>dias.map(()=>0));
    const nowLocal = new Date();

    for (let i=0;i<linhas.length;i++){
      const tearCod = linhas[i].codigo;
      for (let j=0;j<dias.length;j++){
        const day = dias[j];
        const { worked, paradas } = computeDayTotalsForTear(day, tearCod, selTurnos, turnos, eventos, nowLocal);
        const funcionando = Math.max(0, worked - paradas);
        mMins[i][j] = (modo === "funcionando") ? funcionando : paradas;
      }
    }

    const totalLinhaM = mMins.map(r=>r.reduce((s,n)=>s+n,0));
    const totalColunaM = dias.map((_,j)=>mMins.reduce((s,row)=>s+row[j],0));
    const totalGeralM = totalColunaM.reduce((s,n)=>s+n,0);

    const toH = (x:number)=>minutesToHours(x);
    return {
      matriz: mMins.map(r=>r.map(toH)),
      totalLinha: totalLinhaM.map(toH),
      totalColuna: totalColunaM.map(toH),
      totalGeral: toH(totalGeralM),
      linhas
    };
  }, [teares, selTeares, dias, eventos, turnos, selTurnos, modo]);

  const toggleTear = (n: number) => setSelTeares(prev => { const s=new Set(prev); s.has(n)?s.delete(n):s.add(n); return s; });
  const toggleAllTeares = () => setSelTeares(prev => prev.size===teares.length && teares.length>0 ? new Set() : new Set(teares.map(x=>Number(x.codigo))));

  /* -------- gráfico (1 tear) -------- */
  const [gDtIni, setGDtIni] = useState<string>(() => dtIni);
  const [gDtFim, setGDtFim] = useState<string>(() => dtFim);
  const [gTear, setGTear] = useState<number | null>(null);

  const gDias = useMemo(() => {
    const out: Date[] = [];
    let d = startOfDay(parseLocalYmd(gDtIni));
    const fim = startOfDay(parseLocalYmd(gDtFim));
    while (d <= fim) { out.push(new Date(d)); d = addDays(d, 1); }
    return out;
  }, [gDtIni, gDtFim]);

  useEffect(() => { if (gTear == null && teares.length) setGTear(Number(teares[0].codigo)); }, [teares, gTear]);

  const { serieParado, serieFunc, gLabels } = useMemo(() => {
    const labels = gDias.map(d => fmtDiaLabel(d));
    if (!gTear) return { serieParado: [], serieFunc: [], gLabels: labels };

    const nowLocal = new Date();
    const parados: number[] = [];
    const funcs: number[] = [];

    for (const day of gDias) {
      const { worked, paradas } = computeDayTotalsForTear(day, gTear, gTurnos, turnos, eventos, nowLocal);
      const func = Math.max(0, worked - paradas);
      parados.push(minutesToHours(paradas));
      funcs.push(minutesToHours(func));
    }
    return { serieParado: parados, serieFunc: funcs, gLabels: labels };
  }, [gDias, gTurnos, gTear, turnos, eventos]);

  const gTearName = useMemo(() => {
    if (gTear == null) return "";
    const t = teares.find(tt => Number(tt.codigo) === Number(gTear));
    return t?.nome ?? "";
  }, [gTear, teares]);

  /* -------- Paradas por Motivo (1 tear) -------- */
  const [mDtIni, setMDtIni] = useState<string>(() => dtIni);
  const [mDtFim, setMDtFim] = useState<string>(() => dtFim);
  const [mTear, setMTear] = useState<number | null>(null);

  // motivos selecionados (checkboxes)
  const [selMotivos, setSelMotivos] = useState<Set<number>>(new Set());
  useEffect(() => { setSelMotivos(new Set(motivos.map(m => m.codigo))); }, [motivos]);
  useEffect(() => { if (mTear == null && teares.length) setMTear(Number(teares[0].codigo)); }, [teares, mTear]);

  const mDias = useMemo(() => {
    const out: Date[] = [];
    let d = startOfDay(parseLocalYmd(mDtIni));
    const fim = startOfDay(parseLocalYmd(mDtFim));
    while (d <= fim) { out.push(new Date(d)); d = addDays(d, 1); }
    return out;
  }, [mDtIni, mDtFim]);

  const mTearName = useMemo(() => {
    if (mTear == null) return "";
    const t = teares.find(tt => Number(tt.codigo) === Number(mTear));
    return t?.nome ?? "";
  }, [mTear, teares]);

  const motivoTable = useMemo(() => {
    const labels = mDias.map(d => fmtDiaLabel(d));
    if (!mTear) {
      return {
        labels,
        rows: [] as Array<{codigo:number; descricao:string; cells:number[]; total:number}>,
        colTotals: [] as number[],
        grand: 0
      };
    }

    const nowLocal = new Date();
    const rowsAll = motivos.map(m => ({
      codigo: m.codigo,
      descricao: m.descricao,
      mins: Array(mDias.length).fill(0) as number[]
    }));

    const motivoIndex = new Map<number, number>();
    motivos.forEach((m, idx) => motivoIndex.set(m.codigo, idx));

    mDias.forEach((day, j) => {
      const mp = computeParadasPorMotivoDia(day, mTear, mTurnos, turnos, eventos, nowLocal);
      for (const [mot, mins] of mp) {
        const idx = motivoIndex.get(mot);
        if (idx != null) rowsAll[idx].mins[j] += mins;
      }
    });

    const rowsFiltered = rowsAll.filter(r => selMotivos.has(r.codigo));
    const colTotalsM = mDias.map((_,j)=> rowsFiltered.reduce((s,r)=> s + (r.mins[j]||0), 0));
    const grandM = colTotalsM.reduce((s,n)=> s+n, 0);

    return {
      labels,
      rows: rowsFiltered.map(r => ({
        codigo: r.codigo,
        descricao: r.descricao,
        cells: r.mins.map(minutesToHours),
        total: minutesToHours(r.mins.reduce((s,n)=>s+n,0))
      })),
      colTotals: colTotalsM.map(minutesToHours),
      grand: minutesToHours(grandM),
    };
  }, [mDias, mTear, mTurnos, motivos, turnos, eventos, selMotivos]);

  /* ====================== UI ====================== */

  return (
    <div className="container-fluid py-3">
      <div className="row g-3">
        {/* ===== Parte superior (tabela de funcionamento/parado) ===== */}
        <div className="col-12">
          <div className="card shadow-sm">
            <div className="card-body">
              <div className="d-flex align-items-center justify-content-between mb-3">
                <h2 className="h3 m-0">Relatório 1º Turno</h2>
                <button className="btn btn-outline-secondary" onClick={() => navigate('/')}>Sair</button>
              </div>

              <div className="row g-3">
                <div className="col-12 col-md-3">
                  <label className="form-label">Data início</label>
                  <input type="date" className="form-control" value={dtIni} onChange={e=>setDtIni(e.target.value)} />
                </div>
                <div className="col-12 col-md-3">
                  <label className="form-label">Data fim</label>
                  <input type="date" className="form-control" value={dtFim} onChange={e=>setDtFim(e.target.value)} />
                </div>
                <div className="col-12 col-md-3">
                  <label className="form-label">Modo</label>
                  <div className="btn-group w-100">
                    <button className={`btn ${modo==="funcionando"?"btn-success":"btn-outline-secondary"}`} onClick={()=>setModo("funcionando")}>Funcionando</button>
                    <button className={`btn ${modo==="parado"?"btn-danger":"btn-outline-secondary"}`} onClick={()=>setModo("parado")}>Parado</button>
                  </div>
                </div>

                {/* Turno fixo */}
                <div className="col-12 col-md-3">
                  <label className="form-label">Turno</label>
                  <div className="form-control-plaintext fw-bold text-success pt-2">1º turno (fixo)</div>
                </div>

                <div className="col-12">
                  <label className="form-label">Teares</label>
                  <div className="d-flex flex-wrap gap-3">
                    <label className="form-check">
                      <input className="form-check-input" type="checkbox"
                        checked={selTeares.size===teares.length && teares.length>0}
                        onChange={toggleAllTeares}/>
                      <strong className="form-check-label">Selecionar todos</strong>
                    </label>
                    {teares.map(t=>(
                      <label key={`tear-${t.codigo}`} className="form-check">
                        <input className="form-check-input" type="checkbox"
                          checked={selTeares.has(Number(t.codigo))}
                          onChange={()=>toggleTear(Number(t.codigo))}/>
                        <span className="form-check-label">{t.nome}</span>
                      </label>
                    ))}
                  </div>
                  <div className="text-muted small mt-2">
                    Usa <code>/turnos</code> por dia e <code>/eventos</code> para horas paradas (apenas 1º turno).
                  </div>
                </div>
              </div>

              <div className="table-responsive mt-3">
                <table className="table table-bordered align-middle m-0 report-table">
                  <thead className="table-light">
                    <tr>
                      <th className="sticky-col">Tear</th>
                      {dias.map((d, idx) => <th key={`dia-${idx}`}>{fmtDiaLabel(d)}</th>)}
                      <th>Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {linhas.map((t, i) => (
                      <tr key={`row-${t.codigo}`}>
                        <td className="sticky-col text-start">{t.nome}</td>
                        {matriz[i].map((v, j) => (
                          <td key={`c-${t.codigo}-${j}`}>{fmtHM(v)}</td>
                        ))}
                        <td className="fw-bold bg-success-subtle">{fmtHM(totalLinha[i])}</td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot className="table-light">
                    <tr>
                      <th className="sticky-col">Total</th>
                      {totalColuna.map((v, j) => <th key={`tot-${j}`}>{fmtHM(v)}</th>)}
                      <th>{fmtHM(totalGeral)}</th>
                    </tr>
                  </tfoot>
                </table>
              </div>

            </div>
          </div>
        </div>

        {/* ===== Gráfico (um tear) ===== */}
        <div className="col-12">
          <div className="card shadow-sm">
            <div className="card-body">
              <h3 className="h5 mb-3">
                Controle de Paradas — Gráfico {gTearName ? `(${gTearName})` : "(1 tear)"} — 1º turno
              </h3>

              <div className="row g-3">
                <div className="col-12 col-md-3">
                  <label className="form-label">Data início</label>
                  <input type="date" className="form-control" value={gDtIni} onChange={e=>setGDtIni(e.target.value)} />
                </div>
                <div className="col-12 col-md-3">
                  <label className="form-label">Data fim</label>
                  <input type="date" className="form-control" value={gDtFim} onChange={e=>setGDtFim(e.target.value)} />
                </div>

                {/* Turno fixo */}
                <div className="col-12 col-md-3">
                  <label className="form-label">Turno</label>
                  <div className="form-control-plaintext fw-bold text-success pt-2">1º turno (fixo)</div>
                </div>

                <div className="col-12">
                  <label className="form-label">Tear (somente 1)</label>
                  <div className="d-flex flex-wrap gap-3">
                    {teares.map(t => (
                      <label key={`radio-${t.codigo}`} className="form-check">
                        <input
                          className="form-check-input"
                          type="radio"
                          name="tearGrafico"
                          checked={gTear === Number(t.codigo)}
                          onChange={() => setGTear(Number(t.codigo))}
                        />
                        <span className="form-check-label">{t.nome}</span>
                      </label>
                    ))}
                  </div>
                </div>
              </div>

              <div className="mt-4">
                {gTear ? (
                  <LineChart labels={gLabels} seriesA={serieParado} seriesB={serieFunc} />
                ) : (
                  <div className="text-muted">Selecione um tear para gerar o gráfico.</div>
                )}
              </div>

            </div>
          </div>
        </div>

        {/* ===== Paradas por Motivo (1 tear) ===== */}
        <div className="col-12">
          <div className="card shadow-sm">
            <div className="card-body">
              <h3 className="h5 mb-3">Paradas por Motivo — {mTearName ? `(${mTearName})` : "(1 tear)"} — 1º turno</h3>

              <div className="row g-3">
                <div className="col-12 col-md-3">
                  <label className="form-label">Data início</label>
                  <input type="date" className="form-control" value={mDtIni} onChange={e=>setMDtIni(e.target.value)} />
                </div>
                <div className="col-12 col-md-3">
                  <label className="form-label">Data fim</label>
                  <input type="date" className="form-control" value={mDtFim} onChange={e=>setMDtFim(e.target.value)} />
                </div>

                {/* Turno fixo */}
                <div className="col-12 col-md-3">
                  <label className="form-label">Turno</label>
                  <div className="form-control-plaintext fw-bold text-success pt-2">1º turno (fixo)</div>
                </div>

                <div className="col-12">
                  <label className="form-label">Tear (somente 1)</label>
                  <div className="d-flex flex-wrap gap-3">
                    {teares.map(t => (
                      <label key={`mradio-${t.codigo}`} className="form-check">
                        <input
                          className="form-check-input"
                          type="radio"
                          name="tearMotivo"
                          checked={mTear === Number(t.codigo)}
                          onChange={() => setMTear(Number(t.codigo))}
                        />
                        <span className="form-check-label">{t.nome}</span>
                      </label>
                    ))}
                  </div>
                </div>

                {/* Checkboxes de motivos */}
                <div className="col-12">
                  <label className="form-label">Motivos</label>
                  <div className="d-flex flex-wrap gap-3">
                    <label className="form-check">
                      <input
                        className="form-check-input"
                        type="checkbox"
                        checked={selMotivos.size === motivos.length && motivos.length>0}
                        onChange={()=>{
                          setSelMotivos(prev =>
                            prev.size === motivos.length ? new Set() : new Set(motivos.map(m => m.codigo))
                          );
                        }}
                      />
                      <strong className="form-check-label">Selecionar todos</strong>
                    </label>
                    {motivos.map(m => (
                      <label key={`mot-${m.codigo}`} className="form-check">
                        <input
                          className="form-check-input"
                          type="checkbox"
                          checked={selMotivos.has(m.codigo)}
                          onChange={()=>{
                            setSelMotivos(prev => {
                              const s = new Set(prev);
                              s.has(m.codigo) ? s.delete(m.codigo) : s.add(m.codigo);
                              return s;
                            });
                          }}
                        />
                        <span className="form-check-label">{m.descricao}</span>
                      </label>
                    ))}
                  </div>
                </div>
              </div>

              <div className="table-responsive mt-3">
                <table className="table table-bordered align-middle m-0">
                  <thead className="table-light">
                    <tr>
                      <th style={{minWidth:90}}>Código</th>
                      <th>Motivo</th>
                      {motivoTable.labels.map((lb, i) => (
                        <th key={`mlb-${i}`}>{lb}</th>
                      ))}
                      <th>Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {motivoTable.rows.map(r => (
                      <tr key={`mrow-${r.codigo}`}>
                        <td>{r.codigo}</td>
                        <td className="text-start">{r.descricao}</td>
                        {r.cells.map((v, j) => <td key={`mcell-${r.codigo}-${j}`}>{fmtHM(v)}</td>)}
                        <td className="fw-bold bg-success-subtle">{fmtHM(r.total)}</td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot className="table-light">
                    <tr>
                      <th colSpan={2} className="text-end">Total</th>
                      {motivoTable.colTotals.map((v, j) => <th key={`mtot-${j}`}>{fmtHM(v)}</th>)}
                      <th>{fmtHM(motivoTable.grand)}</th>
                    </tr>
                  </tfoot>
                </table>
              </div>

            </div>
          </div>
        </div>
      </div>

      <style>{`
        .report-table thead th { position: sticky; top: 0; z-index: 1; }
        .report-table .sticky-col { position: sticky; left: 0; background: #fff; z-index: 2; }
      `}</style>
    </div>
  );
}

/* ======================= Gráfico (com rótulos HH:MM) ======================= */
function LineChart({
  width = 900,
  height = 300,
  labels,
  seriesA, // Parado (vermelho)
  seriesB, // Funcionando (verde)
}: {
  width?: number;
  height?: number;
  labels: string[];
  seriesA: number[];
  seriesB: number[];
}) {
  const pad = { left: 50, right: 20, top: 20, bottom: 40 };
  const w = width - pad.left - pad.right;
  const h = height - pad.top - pad.bottom;

  const all = [...seriesA, ...seriesB];
  const yMaxLocal = Math.max(1, ...all);
  const yScale = (v: number) => pad.top + h - (v / yMaxLocal) * h;
  const xScale = (i: number) => pad.left + (labels.length <= 1 ? 0 : (w * i) / (labels.length - 1));
  const toPath = (arr: number[]) => arr.map((v, i) => `${i ? "L" : "M"} ${xScale(i)} ${yScale(v || 0)}`).join(" ");

  return (
    <svg width="100%" viewBox={`0 0 ${width} ${height}`}>
      <line x1={pad.left} y1={pad.top} x2={pad.left} y2={pad.top + h} stroke="#cbd5e1" />
      <line x1={pad.left} y1={pad.top + h} x2={pad.left + w} y2={pad.top + h} stroke="#cbd5e1" />
      {[0, 0.5, 1].map((p, idx) => (
        <line key={idx} x1={pad.left} x2={pad.left + w} y1={pad.top + h - h * p} y2={pad.top + h - h * p} stroke="#e2e8f0" />
      ))}

      <path d={toPath(seriesA)} fill="none" stroke="#ef4444" strokeWidth={2} />
      <path d={toPath(seriesB)} fill="none" stroke="#10b981" strokeWidth={2} />

      {seriesA.map((v,i)=>(
        <g key={`a-${i}`}>
          <circle cx={xScale(i)} cy={yScale(v||0)} r="4" fill="#ef4444" />
          <text x={xScale(i)} y={yScale(v||0)-8} textAnchor="middle" fontSize="11" fill="#ef4444">{fmtHM(v)}</text>
        </g>
      ))}
      {seriesB.map((v,i)=>(
        <g key={`b-${i}`}>
          <circle cx={xScale(i)} cy={yScale(v||0)} r="4" fill="#10b981" />
          <text x={xScale(i)} y={yScale(v||0)+14} textAnchor="middle" fontSize="11" fill="#10b981">{fmtHM(v)}</text>
        </g>
      ))}

      {/* legenda canto superior esquerdo */}
      <g transform={`translate(${pad.left + 6}, ${pad.top + 16})`}>
        <circle cx="0" cy="0" r="5" fill="#ef4444" />
        <text x="10" y="0" dominantBaseline="central" fontSize="13">Parado</text>
        <circle cx="90" cy="0" r="5" fill="#10b981" />
        <text x="100" y="0" dominantBaseline="central" fontSize="13">Funcionando</text>
      </g>

      {labels.map((lb, i) => (
        <text key={i} x={xScale(i)} y={pad.top + h + 18} textAnchor="middle" fontSize="11">{lb}</text>
      ))}
    </svg>
  );
}
