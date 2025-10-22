import React from 'react'
import { useEffect, useState } from 'react'
import { get, post, put, del } from '../api'

type Usuario = { cod:number; nome:string; role:number }

export default function Usuarios(){
  const [rows, setRows] = useState<Usuario[]>([])
  const [nome, setNome] = useState('')
  const [senha, setSenha] = useState('')
  const [role, setRole] = useState(1)
  const [msg, setMsg] = useState(''); const [erro, setErro] = useState('')

  async function load(){
    setErro('')
    try{ setRows(await get<Usuario[]>('/usuarios')) }
    catch(e:any){ setErro(e?.message || 'Erro ao carregar') }
  }
  useEffect(()=>{ load() }, [])

  async function add(){
    setErro(''); setMsg('')
    try{
      await post('/usuarios', { nome, senha, role })
      setNome(''); setSenha(''); setRole(1); setMsg('Criado')
      load()
    }catch(e:any){ setErro(e?.message || 'Erro ao criar') }
  }

  async function renomear(u:Usuario){
    const n = prompt('Novo nome', u.nome); if(n==null) return
    try{ await put(`/usuarios/${u.cod}`, { nome:n }); setMsg('Nome atualizado'); load() }
    catch(e:any){ setErro(e?.message || 'Erro') }
  }

  async function mudarSenha(u:Usuario){
    const s = prompt('Nova senha'); if(s==null || !s) return
    try{ await put(`/usuarios/${u.cod}`, { senha:s }); setMsg('Senha atualizada'); load() }
    catch(e:any){ setErro(e?.message || 'Erro') }
  }

  async function mudarRole(u:Usuario){
    const r = Number(prompt(
      'Perfil (1=Líder 1º, 2=Líder 2º, 3=Líder 3º, 4=Processos, 5=Gestor, 6=TI)',
      String(u.role)
    ))
    if(!r) return
    try{ await put(`/usuarios/${u.cod}`, { role:r }); setMsg('Perfil atualizado'); load() }
    catch(e:any){ setErro(e?.message || 'Erro') }
  }

  async function remover(u:Usuario){
    if(!confirm('Excluir usuário?')) return
    try{ await del(`/usuarios/${u.cod}`); setMsg('Excluído'); load() }
    catch(e:any){ setErro(e?.message || 'Erro') }
  }

  return (
    <div className="container py-3">
      <div className="d-flex align-items-center justify-content-between mb-3">
        <a href="/" className="btn btn-link p-0">&larr; Menu</a>
        <h1 className="h5 m-0">Usuários</h1>
        <button className="btn btn-outline-secondary btn-sm" onClick={()=>{localStorage.clear(); location.href='/login'}}>Sair</button>
      </div>

      {erro && <div className="alert alert-danger">{erro}</div>}
      {msg && <div className="alert alert-success">{msg}</div>}

      <div className="card">
        <div className="card-body">
          <div className="row g-2 align-items-end">
            <div className="col-12 col-md">
              <label className="form-label">Nome</label>
              <input className="form-control" value={nome} onChange={e=>setNome(e.target.value)} />
            </div>
            <div className="col-12 col-md">
              <label className="form-label">Senha</label>
              <input type="password" className="form-control" value={senha} onChange={e=>setSenha(e.target.value)} />
            </div>
            <div className="col-12 col-md-3">
              <label className="form-label">Perfil</label>
              <select className="form-select" value={role} onChange={e=>setRole(Number(e.target.value))}>
                <option value={1}>1 — Líder 1º Turno</option>
                <option value={2}>2 — Líder 2º Turno</option>
                <option value={3}>3 — Líder 3º Turno</option>
                <option value={4}>4 — Processos</option>
                <option value={5}>5 — Gestor</option>
                <option value={6}>6 — TI</option>
              </select>
            </div>
            <div className="col-12 col-md-auto">
              <button className="btn btn-success" onClick={add}>Adicionar</button>
            </div>
          </div>
        </div>
      </div>

      <div className="mt-3 table-responsive">
        <table className="table table-sm align-middle">
          <thead><tr><th>Cód</th><th>Nome</th><th>Perfil</th><th style={{width:260}}>Ações</th></tr></thead>
          <tbody>
            {rows.map(u=>(
              <tr key={u.cod}>
                <td>{u.cod}</td>
                <td>{u.nome}</td>
                <td>{u.role}</td>
                <td className="d-flex gap-2">
                  <button className="btn btn-outline-primary btn-sm" onClick={()=>renomear(u)}>Renomear</button>
                  <button className="btn btn-outline-warning btn-sm" onClick={()=>mudarSenha(u)}>Senha</button>
                  <button className="btn btn-outline-secondary btn-sm" onClick={()=>mudarRole(u)}>Perfil</button>
                  <button className="btn btn-outline-danger btn-sm" onClick={()=>remover(u)}>Excluir</button>
                </td>
              </tr>
            ))}
            {rows.length===0 && <tr><td colSpan={4}>Sem usuários (além do admin)</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  )
}
