// web/src/ModalRegistro.tsx
import React, { useEffect, useRef, useState } from 'react'
import { get, post } from './api'
import type { Motivo, NovoRegistro } from './types'

export type Modo = 'parada' | 'funcionando'

/**
 * Definição dos turnos:
 * 1: 05:00–13:30
 * 2: 13:30–22:00
 * 3: 22:00–05:00 (+1 dia)
 */
const TOL_MIN = 10 // tolerância de 10 minutos pós-virada

function atDate(base: Date, hm: string) {
  const [h, m] = hm.split(':').map(Number)
  const d = new Date(base)
  d.setHours(h, m, 0, 0)
  return d
}

function turnoEfetivo(dt: Date) {
  const b = new Date(dt)
  const t1_start = atDate(b, '05:00')
  const t2_start = atDate(b, '13:30')
  const t3_start = atDate(b, '22:00')
  const next_day_5 = new Date(atDate(b, '05:00').getTime() + 24 * 60 * 60 * 1000)

  // Faixas base
  const t1 = { id: 1 as const, start: t1_start, end: t2_start }
  const t2 = { id: 2 as const, start: t2_start, end: t3_start }
  const t3 = { id: 3 as const, start: t3_start, end: next_day_5 }

  // Tolerância: nos primeiros TOL_MIN do turno, ainda pertence ao turno anterior
  const t1_tol = new Date(t1.start.getTime() + TOL_MIN * 60 * 1000)
  const t2_tol = new Date(t2.start.getTime() + TOL_MIN * 60 * 1000)
  const t3_tol = new Date(t3.start.getTime() + TOL_MIN * 60 * 1000)

  // Dentro de cada janela
  if (dt >= t1.start && dt < t2.start) {
    if (dt < t1_tol) return 3 // ainda conta como final do 3º
    return 1
  }
  if (dt >= t2.start && dt < t3.start) {
    if (dt < t2_tol) return 1
    return 2
  }
  // 22:00 -> 05:00(+1)
  if (dt >= t3.start || dt < t1.start) {
    // se está entre 22:00 e 22:10 ainda pertence ao 2º turno
    if (dt >= t3.start && dt < t3_tol) return 2
    return 3
  }

  return 1
}

function toInputLocalValue(d: Date) {
  const p = (n:number)=>String(n).padStart(2,'0')
  return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`
}

function formatHoras(h?: number) {
  if (h == null || isNaN(h)) return ''
  let hh = Math.floor(h)
  let mm = Math.round((h - hh) * 60)
  if (mm === 60) { hh += 1; mm = 0 }
  return `${hh}:${String(mm).padStart(2, '0')}h`
}

type Props = {
  tear: number
  modo: Modo
  role: number // papel do usuário logado
  desde?: string
  horas?: number
  onClose: () => void
  onSaved: () => void
}

export default function ModalRegistro({
  tear, modo, role, desde, horas, onClose, onSaved
}: Props) {
  const [motivos, setMotivos] = useState<Motivo[]>([])
  const [dataHora, setDataHora] = useState<string>('')
  const [motivo, setMotivo] = useState<number | ''>('')
  const [erro, setErro] = useState<string>('')

  const titulo = modo === 'parada' ? 'Registrar Parada' : 'Registrar Funcionando'
  const timeInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (modo === 'parada') {
      get<Motivo[]>('/motivos').then(setMotivos).catch(() => {})
    }
    setDataHora(toInputLocalValue(new Date()))
  }, [modo])

  useEffect(() => {
    timeInputRef.current?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const agoraBtn = () => setDataHora(toInputLocalValue(new Date()))

  const salvar = async () => {
    try {
      setErro('')

      // 4 e 5: nunca podem registrar
      if (role === 4 || role === 5) {
        setErro('Seu perfil não está autorizado a registrar paradas/funcionamento.')
        return
      }

      const sel = new Date(dataHora)
      const agora = new Date()

      // Bloqueio universal de FUTURO (inclusive para role 6)
      if (sel.getTime() > agora.getTime()) {
        setErro('Não é permitido registrar no futuro.')
        return
      }

      // role 6 pode qualquer horário (passado e qualquer turno)
      if (role !== 6) {
        const turnoSel = turnoEfetivo(sel)
        const turnoAgora = turnoEfetivo(agora)

        // Deve estar no turno atual (com tolerância de 10 min)
        if (turnoSel !== turnoAgora) {
          setErro('Horário informado pertence a outro turno (fora da tolerância de 10 minutos).')
          return
        }

        // Roles 1/2/3 devem bater com o seu próprio turno
        if ([1,2,3].includes(role) && turnoSel !== role) {
          setErro(`Seu perfil só pode registrar no ${role}º turno.`)
          return
        }
      }

      // Motivo obrigatório para parada
      if (modo === 'parada' && (motivo === '' || motivo === undefined || motivo === null)) {
        setErro('Selecione um motivo para registrar a parada.')
        return
      }

      const payload: NovoRegistro = {
        tear,
        data_hora: sel.toISOString(),
        ...(modo === 'parada' ? { motivo: Number(motivo) } : {}),
      }
      const path = modo === 'parada' ? '/parada' : '/funcionando'
      await post(path, payload)
      onSaved()
    } catch (e: any) {
      setErro(e?.message ?? 'Erro ao salvar')
    }
  }

  const modalBox: React.CSSProperties = {
    background: '#fff',
    padding: 28,
    width: 'min(880px, 96vw)',
    borderRadius: 16,
    boxShadow: '0 20px 60px rgba(0,0,0,0.2)'
  }
  const titleStyle: React.CSSProperties = {
    marginTop: 0,
    marginBottom: 6,
    fontSize: 'clamp(1.5rem, 2.6vw, 2rem)',
    fontWeight: 800
  }
  const infoStyle: React.CSSProperties = {
    fontSize: 'clamp(1rem, 1.8vw, 1.25rem)'
  }
  const labelStyle: React.CSSProperties = {
    fontSize: 'clamp(1rem, 1.8vw, 1.25rem)',
    fontWeight: 600,
    marginBottom: 6
  }
  const inputStyle: React.CSSProperties = {
    width: '100%',
    height: 56,
    fontSize: 'clamp(1rem, 1.8vw, 1.25rem)',
    padding: '10px 14px',
    borderRadius: 12,
    border: '1px solid #d1d5db'
  }
  const btnPrimary: React.CSSProperties = {
    height: 56,
    padding: '0 22px',
    fontSize: 'clamp(1rem, 1.8vw, 1.1rem)',
    fontWeight: 700,
    borderRadius: 12,
    border: '1px solid #16a34a',
    background: '#22c55e',
    color: '#0b2e18',
    cursor: 'pointer'
  }
  const btnGhost: React.CSSProperties = {
    height: 56,
    padding: '0 22px',
    fontSize: 'clamp(1rem, 1.8vw, 1.1rem)',
    fontWeight: 700,
    borderRadius: 12,
    border: '1px solid #9ca3af',
    background: '#fff',
    color: '#111827',
    cursor: 'pointer'
  }
  const btnNow: React.CSSProperties = {
    height: 56,
    padding: '0 16px',
    fontSize: 'clamp(0.95rem, 1.6vw, 1.05rem)',
    fontWeight: 700,
    borderRadius: 12,
    border: '1px solid #9ca3af',
    background: '#f3f4f6',
    cursor: 'pointer',
    whiteSpace: 'nowrap'
  }

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', display: 'grid', placeItems: 'center', zIndex: 1050 }}>
      <div style={modalBox}>
        <h2 style={titleStyle}>{titulo}</h2>

        <p style={infoStyle}><b>Tear:</b> {String(tear).padStart(2, '0')}</p>

        {desde && (
          <p style={infoStyle}>
            <b>{modo === 'parada' ? 'Funcionando desde:' : 'Parado desde:'}</b>{' '}
            {new Date(desde).toLocaleString()} &nbsp; ({formatHoras(horas)})
          </p>
        )}

        <div style={{ display: 'grid', gap: 18, marginTop: 16 }}>
          <div>
            <div style={{ fontSize: 18, color: '#6b7280', margin: '4px 0 8px' }}>
              Sem permitir <b>futuro</b> e respeitando o <b>turno atual</b> (tolerância {TOL_MIN} min). TI (role 6) pode qualquer horário passado.
            </div>
            <div style={labelStyle}>Data e Hora:</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 12 }}>
              <input
                ref={timeInputRef}
                type="datetime-local"
                value={dataHora}
                onChange={(e) => setDataHora(e.target.value)}
                style={inputStyle}
              />
              <button type="button" onClick={agoraBtn} style={btnNow}>Agora</button>
            </div>
          </div>

          {modo === 'parada' && (
            <div>
              <div style={labelStyle}>Motivo:</div>
              <select
                value={motivo}
                onChange={(e) => setMotivo(e.target.value)}
                style={inputStyle}
              >
                <option value="">Selecione...</option>
                {motivos.map((m) => (
                  <option key={m.codigo} value={m.codigo}>
                    {m.codigo} — {m.descricao}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>

        {erro && <div style={{ color: 'crimson', marginTop: 12, fontSize: '1rem' }}>{erro}</div>}

        <div style={{ display: 'flex', gap: 12, marginTop: 22, flexWrap: 'wrap' }}>
          <button type="button" onClick={salvar} style={btnPrimary}>Salvar</button>
          <button type="button" onClick={onClose} style={btnGhost}>Voltar</button>
        </div>
      </div>
    </div>
  )
}
