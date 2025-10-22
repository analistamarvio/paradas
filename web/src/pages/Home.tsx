import React, { useEffect, useMemo } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { can, type Recurso } from '../perm' // pode continuar usando no Guard das rotas
import './home.css'

type TileItem = { to: string; title: string; recurso?: Recurso; accent?: boolean }

function Tile({
  to,
  title,
  accent = false,
  onClick,
}: {
  to: string
  title: string
  accent?: boolean
  onClick?: React.MouseEventHandler<HTMLAnchorElement>
}) {
  return (
    <Link
      to={to}
      onClick={onClick}
      className={`tile d-flex align-items-center justify-content-center text-decoration-none rounded-3 shadow-sm ${
        accent ? 'tile-accent' : 'tile-main'
      }`}
    >
      <span className="tile-text">{title}</span>
    </Link>
  )
}

export default function Home() {
  const navigate = useNavigate()

  // redireciona para login se não tiver sessão
  useEffect(() => {
    if (!localStorage.getItem('token') || !localStorage.getItem('user')) {
      navigate('/login', { replace: true })
    }
  }, [navigate])

  const role = useMemo(() => {
    try {
      const raw = localStorage.getItem('user')
      if (!raw) return 0
      const u = JSON.parse(raw) as { role?: number }
      return Number(u?.role || 0)
    } catch {
      return 0
    }
  }, [])

  // === Menu determinístico por perfil ===
  // - Dashboard sempre
  // - Role 1: Relatório 1º Turno
  // - Role 2: Relatório 2º Turno (somente ele)
  // - Role 3: Relatório 3º Turno
  // - Roles 4 e 6: telas de cadastro (Turnos/Teares/Motivos)
  // - Roles 5 e 6: "Relatórios" (geral)
  // - "Usuários" só para 6 (TI), se desejar exibir adicione aqui
  const tiles = useMemo<TileItem[]>(() => {
    const arr: TileItem[] = []

    // Dashboard
    arr.push({ to: '/dashboard', title: 'Dashboard', recurso: 'dashboard' as Recurso, accent: true })

    // Relatórios por turno (um por perfil)
    // Relatórios por turno
if (role === 1 || role === 6) {
  arr.push({
    to: '/Relatorio1turno',
    title: 'Relatório 1º Turno',
    recurso: '__Relatorio1turno__' as Recurso,
    accent: true,
  })
}
if (role === 2 || role === 6) {
  arr.push({
    to: '/Relatorio2turno',
    title: 'Relatório 2º Turno',
    recurso: '__Relatorio2turno__' as Recurso,
    accent: true,
  })
}
if (role === 3 || role === 6) {
  arr.push({
    to: '/Relatorio3turno',
    title: 'Relatório 3º Turno',
    recurso: '__Relatorio3turno__' as Recurso,
    accent: true,
  })
}


    // Relatórios (geral) – somente 5 e 6
    if (role === 5 || role === 4 || role === 6) {
      // inserir logo após Dashboard (posição 1)
      arr.splice(1, 0, {
        to: '/relatorios',
        title: 'Relatórios',
        recurso: '__relatorios__' as Recurso,
        accent: true,
      })
    }

    // Telas de cadastro – apenas 4 e 6
    if (role === 4 || role === 6) {
      arr.push({ to: '/turnos', title: 'Turnos', recurso: 'turnos' as Recurso })
      arr.push({ to: '/teares', title: 'Teares', recurso: 'teares' as Recurso })
      arr.push({ to: '/motivos', title: 'Motivos', recurso: 'motivos' as Recurso })
    }

    // Usuários – só TI (6). Descomente se quiser mostrar no menu.
    if (role === 6) {
     arr.push({ to: '/usuarios', title: 'Usuários', recurso: 'usuarios' as Recurso })
     }

    return arr
  }, [role])

  const isLogged = !!localStorage.getItem('token') && !!localStorage.getItem('user')

  const handleLogout = () => {
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    navigate('/login', { replace: true })
  }
  const goLogin = () => navigate('/login')

  return (
    <div className="container-fluid min-vh-100 d-flex align-items-center justify-content-center py-3">
      <div className="container">
        <div className="row g-3">
          {tiles.map(t => (
            <div key={t.to} className="col-12 col-md-6">
              <Tile to={t.to} title={t.title} accent={!!t.accent} />
            </div>
          ))}

          {!isLogged && (
            <div className="col-12 col-md-6">
              <Tile to="/login" title="Entrar" accent onClick={goLogin} />
            </div>
          )}

          {isLogged && (
            <div className="col-12 col-md-6">
              <Tile to="/login" title="Sair" accent onClick={handleLogout} />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
