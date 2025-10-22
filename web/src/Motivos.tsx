import React from 'react'
import { useEffect, useState } from 'react'
import { get } from './api'
import { saveMotivo, deleteMotivo } from './api'
import type { Motivo } from './types'
import { Link } from 'react-router-dom'


export default function Motivos(){
  const [rows, setRows] = useState<Motivo[]>([])
  const [codigo, setCodigo] = useState<string>('')
  const [descricao, setDescricao] = useState<string>('')
  const [msg, setMsg] = useState<string>('') 
  const [erro, setErro] = useState<string>('')

  async function load(){
    setErro('')
    try{
      const r = await get<Motivo[]>('/motivos')
      r.sort((a,b)=> a.codigo - b.codigo)
      setRows(r)
    }catch(e:any){
      setErro('Falha ao carregar: ' + (e?.message || ''))
    }
  }
  useEffect(()=>{ load() }, [])

  async function onAdd(){
    setMsg(''); setErro('')
    const cod = Number(codigo)
    if(!cod || !descricao.trim()){ setErro('Preencha código e descrição.'); return }
    try{
      await saveMotivo({ codigo: cod, descricao: descricao.trim() })
      setCodigo(''); setDescricao(''); setMsg('Salvo!')
      load()
    }catch(e:any){
      setErro('Erro ao salvar: ' + (e?.message || ''))
    }
  }

  async function onEdit(m: Motivo){
    const novo = prompt('Descrição:', m.descricao)
    if(novo==null) return
    try{
      await saveMotivo({ codigo: m.codigo, descricao: novo })
      setMsg('Atualizado!'); load()
    }catch(e:any){ setErro('Erro: ' + (e?.message||'')) }
  }

  async function onDelete(codigo: number){
    if(!confirm('Excluir motivo ' + codigo + '?')) return
    try{
      await deleteMotivo(codigo)
      setMsg('Excluído!'); load()
    }catch(e:any){ setErro('Erro: ' + (e?.message||'')) }
  }

  return (
    <div style={{maxWidth:800, margin:'24px auto', fontFamily:'system-ui'}}>
      <h1>Cadastro de Motivos</h1>
          <div className="container py-3">
      <Link to="/" className="btn btn-link mb-3">&larr; Menu</Link>
    </div>

      {erro && <div style={{background:'#fee2e2',border:'1px solid #fecaca',color:'#991b1b',padding:10,borderRadius:8}}>{erro}</div>}

      <div style={{background:'#f9fafb',padding:12,borderRadius:8,border:'1px solid #e5e7eb', marginTop:12}}>
        <div style={{display:'grid',gridTemplateColumns:'120px 1fr 180px',gap:8,fontWeight:600}}>
          <div>Código</div><div>Descrição</div><div>Ações</div>
        </div>

        {rows.map(r=>(
          <div key={r.codigo} style={{display:'grid',gridTemplateColumns:'120px 1fr 180px',gap:8,alignItems:'center',padding:'6px 0',borderTop:'1px dashed #eee'}}>
            <div>{r.codigo}</div>
            <div>{r.descricao}</div>
            <div style={{display:'flex',gap:6}}>
              <button onClick={()=>onEdit(r)}>Editar</button>
              <button onClick={()=>onDelete(r.codigo)} style={{background:'#fecaca'}}>Excluir</button>
            </div>
          </div>
        ))}

        <div style={{display:'grid',gridTemplateColumns:'120px 1fr 180px',gap:8,alignItems:'center',padding:'8px 0',borderTop:'1px dashed #ddd', marginTop:8}}>
          <input type="number" value={codigo} onChange={e=>setCodigo(e.target.value)} placeholder="ex.: 103" />
          <input type="text" value={descricao} onChange={e=>setDescricao(e.target.value)} placeholder="Descrição do motivo" />
          <button onClick={onAdd}>Adicionar</button>
        </div>
      </div>

      {msg && <div style={{marginTop:10, color:'#16a34a'}}>{msg}</div>}
    </div>
  )
}
