import React from 'react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { login } from '../api'

export default function Login(){
  const [nome, setNome] = useState('admin')
  const [senha, setSenha] = useState('admin')
  const [erro, setErro] = useState('')
  const navigate = useNavigate()

  async function onSubmit(e: React.FormEvent){
    e.preventDefault()
    setErro('')
    try{
      const res = await login(nome, senha)
      localStorage.setItem('token', res.token)
      localStorage.setItem('user', JSON.stringify(res.user))
      navigate('/')
    }catch(e:any){
      setErro('Falha no login: ' + (e?.message || ''))
    }
  }

  return (
    <div className="container d-flex align-items-center justify-content-center min-vh-100">
      <form onSubmit={onSubmit} className="p-4 border rounded-3 bg-white shadow-sm" style={{minWidth:320}}>
        <h1 className="h5 mb-3">Entrar</h1>
        {erro && <div className="alert alert-danger py-2">{erro}</div>}
        <div className="mb-2">
          <label className="form-label">Usuário</label>
          <input className="form-control" value={nome} onChange={e=>setNome(e.target.value)} />
        </div>
        <div className="mb-3">
          <label className="form-label">Senha</label>
          <input type="password" className="form-control" value={senha} onChange={e=>setSenha(e.target.value)} />
        </div>
        <button className="btn btn-success w-100">Entrar</button>
      </form>
    </div>
  )
}
