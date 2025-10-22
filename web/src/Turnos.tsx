import React, { useEffect, useState } from 'react'
import { get, saveTurno, deleteTurno } from './api'
import type { Turno } from './types'
import { Link } from 'react-router-dom'

const dias = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom']

// ------ helpers de tempo ------
function parseHM(hm: string): number {
  // retorna minutos
  const [h, m] = hm.split(':').map(Number)
  return (h * 60) + (m || 0)
}
function diffHMBruto(inicio: string, fim: string): number {
  // diferença bruta (em minutos), aceitando cruzar a meia-noite
  const ini = parseHM(inicio)
  let end = parseHM(fim)
  if (end < ini) end += 24 * 60 // vira pro dia seguinte
  return end - ini
}
function fmtHM(mins: number): string {
  const h = Math.floor(mins / 60)
  const m = Math.round(mins % 60)
  return `${h}:${String(m).padStart(2, '0')}`
}

function NovaLinha({ onAdd }: { onAdd: (t: Turno) => void }) {
  const [dia, setDia] = useState<number>(1)
  const [turno, setTurno] = useState<number>(1)
  const [inicio, setInicio] = useState<string>('05:00')
  const [fim, setFim] = useState<string>('14:00')

  const mins = diffHMBruto(inicio, fim)

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: '80px 90px 120px 20px 120px 180px 160px',
        gap: 8,
        alignItems: 'center',
        padding: '8px 0',
        borderTop: '1px dashed #ddd',
      }}
    >
      <select value={dia} onChange={(e) => setDia(Number(e.target.value))}>
        {dias.map((d, i) => (
          <option key={i + 1} value={i + 1}>
            {i + 1} — {d}
          </option>
        ))}
      </select>
      <select value={turno} onChange={(e) => setTurno(Number(e.target.value))}>
        <option value={1}>Turno 1</option>
        <option value={2}>Turno 2</option>
        <option value={3}>Turno 3</option>
      </select>
      <input type="time" value={inicio} onChange={(e) => setInicio(e.target.value)} />
      <span>→</span>
      <input type="time" value={fim} onChange={(e) => setFim(e.target.value)} />
      <div style={{ fontWeight: 600 }}>{fmtHM(mins)}</div>
      <div style={{ display: 'flex', gap: 6 }}>
        <button onClick={() => onAdd({ dia_semana: dia, turno, inicio, fim })}>Adicionar</button>
      </div>
    </div>
  )
}

function Linha({
  row,
  onSave,
  onDelete,
}: {
  row: Turno
  onSave: (t: Turno) => void
  onDelete: (d: number, t: number) => void
}) {
  const [inicio, setInicio] = useState(row.inicio)
  const [fim, setFim] = useState(row.fim)
  const labelDia = `${row.dia_semana} — ${dias[row.dia_semana - 1]}`
  const mins = diffHMBruto(inicio, fim)

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: '80px 90px 120px 20px 120px 180px 160px',
        gap: 8,
        alignItems: 'center',
        padding: '6px 0',
        borderTop: '1px dashed #eee',
      }}
    >
      <div>{labelDia}</div>
      <div>Turno {row.turno}</div>
      <input type="time" value={inicio} onChange={(e) => setInicio(e.target.value)} />
      <span>→</span>
      <input type="time" value={fim} onChange={(e) => setFim(e.target.value)} />
      <div style={{ fontWeight: 600 }}>{fmtHM(mins)}</div>
      <div style={{ display: 'flex', gap: 6 }}>
        <button onClick={() => onSave({ ...row, inicio, fim })}>Salvar</button>
        <button onClick={() => onDelete(row.dia_semana, row.turno)} style={{ background: '#fecaca' }}>
          Excluir
        </button>
      </div>
    </div>
  )
}

export default function Turnos() {
  const [rows, setRows] = useState<Turno[]>([])
  const [loading, setLoading] = useState(true)
  const [msg, setMsg] = useState<string>('')
  const [erro, setErro] = useState<string>('')

  async function load() {
    setLoading(true)
    setErro('')
    try {
      const r = await get<Turno[]>('/turnos')
      r.sort((a, b) => a.dia_semana - b.dia_semana || a.turno - b.turno)
      setRows(r)
    } catch (e: any) {
      setErro('Falha ao carregar turnos: ' + (e?.message || 'erro'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  async function onAdd(t: Turno) {
    setMsg('')
    setErro('')
    try {
      await saveTurno(t)
      setMsg('Turno adicionado/salvo')
      load()
    } catch (e: any) {
      setErro('Erro ao salvar: ' + (e?.message || ''))
    }
  }

  async function onSave(t: Turno) {
    setMsg('')
    setErro('')
    try {
      await saveTurno(t)
      setMsg('Salvo!')
      load()
    } catch (e: any) {
      setErro('Erro ao salvar: ' + (e?.message || ''))
    }
  }

  async function onDelete(dia_semana: number, turno: number) {
    setMsg('')
    setErro('')
    try {
      await deleteTurno(dia_semana, turno)
      load()
    } catch (e: any) {
      setErro('Erro ao excluir: ' + (e?.message || ''))
    }
  }

  return (
    <div style={{ maxWidth: 900, margin: '24px auto', fontFamily: 'system-ui' }}>
      <h1>Cadastro de Turnos</h1>

      {erro && (
        <div style={{ background: '#fee2e2', border: '1px solid #fecaca', color: '#991b1b', padding: 10, borderRadius: 8 }}>
          {erro}
        </div>
      )}

      <div className="container py-3">
        <Link to="/" className="btn btn-link mb-3">&larr; Menu</Link>
        <h1 className="h4">Cadastro de Turnos</h1>
      </div>

      <div style={{ background: '#f9fafb', padding: 12, borderRadius: 8, border: '1px solid #e5e7eb', marginTop: 12 }}>
        {/* Cabeçalho */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '80px 90px 120px 20px 120px 180px 160px',
            gap: 8,
            fontWeight: 600,
          }}
        >
          <div>Dia</div>
          <div>Turno</div>
          <div>Início</div>
          <div></div>
          <div>Fim</div>
          <div>Horas trabalhadas</div>
          <div>Ações</div>
        </div>

        {loading
          ? <p>Carregando...</p>
          : rows.map((r) => (
              <Linha
                key={`${r.dia_semana}-${r.turno}`}
                row={r}
                onSave={onSave}
                onDelete={onDelete}
              />
            ))}

        <NovaLinha onAdd={onAdd} />
      </div>

      {msg && <div style={{ marginTop: 10, color: '#16a34a' }}>{msg}</div>}
    </div>
  )
}
