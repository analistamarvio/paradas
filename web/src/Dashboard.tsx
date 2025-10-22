import React from 'react'
import { useEffect, useState } from 'react'
import type { StatusAtual } from './types'
import { getStatusTeares } from './api'
import ModalRegistro, { Modo } from './ModalRegistro'
import { Link } from 'react-router-dom'

function SairBtn(){
  return <button className="btn btn-outline-secondary btn-sm" onClick={()=>{ localStorage.removeItem('token'); localStorage.removeItem('user'); location.href='/login' }}>Sair</button>
}

// Converte horas decimais para "H:MMh" (ex.: 8.05 -> "8:03h")
function formatHoras(h?: number) {
  if (h == null || isNaN(h)) return ''
  let hh = Math.floor(h)
  let mm = Math.round((h - hh) * 60)
  if (mm === 60) { hh += 1; mm = 0 }
  return `${hh}:${String(mm).padStart(2, '0')}h`
}

export default function Dashboard() {
  const [itens, setItens] = useState<StatusAtual[]>([])
  const [sel, setSel] = useState<{ tear: number; modo: Modo; desde?: string; horas?: number; nome?: string } | null>(null)

  async function load() {
    const rows = await getStatusTeares()
    setItens(rows)
  }
  useEffect(() => {
    load()
    const id = setInterval(load, 5000)
    return () => clearInterval(id)
  }, [])

  function click(tear: number) {
    const st = itens.find(x => x.tear === tear)
    const status = st?.status ?? 1
    const modo: Modo = status === 1 ? 'parada' : 'funcionando'
    setSel({ tear, modo, desde: st?.desde, horas: st?.horas, nome: st?.nome })
  }

  return (
    <div className="container-fluid py-3">
      <div className="container">
        <div className="d-flex align-items-center justify-content-between mb-3">
          <Link to="/" className="btn btn-link p-0">&larr; Menu</Link>
          <h1 className="h5 m-0">Paradas de Tear</h1>
          <div />
        </div>

        {itens.length === 0 && <div className="alert alert-warning">Nenhum tear cadastrado. Cadastre em “Teares”.</div>}

        {/* Máximo 3 colunas: 1 (xs), 2 (md), 3 (lg) */}
        <div className="row row-cols-1 row-cols-md-2 row-cols-lg-3 g-3">
          {itens.map(st => {
            const ok = st.status !== 0
            const tearStr = String(st.tear).padStart(2, '0')
            return (
              <div key={st.tear} className="col">
                <button
                  type="button"
                  onClick={() => click(st.tear)}
                  title={st.nome || `Tear ${tearStr}`}
                  className={`w-100 border-0 rounded-3 shadow-sm tile-btn ${ok ? 'bg-success-subtle' : 'bg-danger-subtle'}`}
                  style={{
                    height: 'clamp(140px, 28vw, 260px)', // grande e responsivo
                    cursor: 'pointer'
                  }}
                >
                  <div className="d-flex flex-column h-100 align-items-center justify-content-center">
                    {/* Nome do tear MAIOR */}
                    <div className="fw-bold"
                         style={{ fontSize: 'clamp(1.2rem, 3.2vw, 1.75rem)', lineHeight: 1.2 }}>
                      {st.nome ?? `Tear ${tearStr}`}
                    </div>

                    {/* Status + tempo MAIOR */}
                    {st.desde && (
                      <div className="text-body-secondary fw-semibold mt-1"
                           style={{ fontSize: 'clamp(1rem, 2.8vw, 1.25rem)' }}>
                        {ok ? 'Funcionando' : 'Parado'} há {formatHoras(st.horas)}
                      </div>
                    )}
                  </div>
                </button>
              </div>
            )
          })}
        </div>
      </div>

      {sel && (
        <ModalRegistro
          tear={sel.tear}
          modo={sel.modo}
          desde={sel.desde}
          horas={sel.horas}
          onClose={() => setSel(null)}
          onSaved={() => {
            setSel(null)
            load()
          }}
        />
      )}
    </div>
  )
}
