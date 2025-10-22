import React from 'react'
import { useEffect, useState } from 'react'
import type { Tear } from './types'
import { listTeares, createTear, renameTear, deleteTearApi } from './api'
import { Link } from 'react-router-dom'


export default function Teares(){
  const [rows, setRows] = useState<Tear[]>([])
  const [nome, setNome] = useState('')
  const [msg, setMsg] = useState('')
  const [erro, setErro] = useState('')

  async function load(){
    setErro('')
    try{
      const r = await listTeares()
      r.sort((a,b)=> a.codigo - b.codigo)
      setRows(r)
    }catch(e:any){
      setErro('Falha ao carregar: ' + (e?.message || ''))
    }
  }
  useEffect(()=>{ load() }, [])

  async function add(){
    setMsg(''); setErro('')
    try{
      await createTear(nome.trim() || undefined)
      setNome(''); setMsg('Tear criado!')
      load()
    }catch(e:any){
      setErro('Erro ao criar: ' + (e?.message || ''))
    }
  }

  async function rename(cod: number){
    const novo = prompt('Novo nome para o tear:', rows.find(r=>r.codigo===cod)?.nome || '')
    if(novo==null) return
    try{
      await renameTear(cod, novo)
      setMsg('Renomeado!')
      load()
    }catch(e:any){
      setErro('Erro ao renomear: ' + (e?.message || ''))
    }
  }

  async function remove(cod: number){
    if(!confirm('Excluir tear ' + cod + '?')) return
    try{
      await deleteTearApi(cod)
      setMsg('Excluído!')
      load()
    }catch(e:any){
      setErro('Erro ao excluir: ' + (e?.message || ''))
    }
  }

  return (

    <div style={{maxWidth:800, margin:'24px auto', fontFamily:'system-ui'}}>
      <h1>Cadastro de Teares</h1>
          <div className="container py-3">
      <Link to="/" className="btn btn-link mb-3">&larr; Menu</Link>
    </div>

      {erro && <div style={{background:'#fee2e2',border:'1px solid #fecaca',color:'#991b1b',padding:10,borderRadius:8}}>{erro}</div>}

      <div style={{background:'#f9fafb',padding:12,borderRadius:8,border:'1px solid #e5e7eb', marginTop:12}}>
        <div style={{display:'grid',gridTemplateColumns:'120px 1fr 180px',gap:8,fontWeight:600}}>
          <div>Código</div><div>Nome</div><div>Ações</div>
        </div>

        {rows.map(r=>(
          <div key={r.codigo} style={{display:'grid',gridTemplateColumns:'120px 1fr 180px',gap:8,alignItems:'center',padding:'6px 0',borderTop:'1px dashed #eee'}}>
            <div>{String(r.codigo).padStart(2,'0')}</div>
            <div>{r.nome}</div>
            <div style={{display:'flex',gap:6}}>
              <button onClick={()=>rename(r.codigo)}>Renomear</button>
              <button onClick={()=>remove(r.codigo)} style={{background:'#fecaca'}}>Excluir</button>
            </div>
          </div>
        ))}

        <div style={{display:'grid',gridTemplateColumns:'120px 1fr 180px',gap:8,alignItems:'center',padding:'8px 0',borderTop:'1px dashed #ddd', marginTop:8}}>
          <div>(auto)</div>
          <input type="text" value={nome} onChange={e=>setNome(e.target.value)} placeholder="(opcional) ex.: tear07" />
          <button onClick={add}>Adicionar</button>
        </div>
      </div>

      {msg && <div style={{marginTop:10, color:'#16a34a'}}>{msg}</div>}
    </div>
  )
}
