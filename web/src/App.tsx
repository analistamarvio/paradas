import React from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import Home from './pages/Home'
import Dashboard from './Dashboard'
import Turnos from './Turnos'
import Teares from './Teares'
import Motivos from './Motivos'
import Login from './pages/Login'
import Usuarios from './pages/Usuarios'
import { RequireAuth } from './perm'   // ✅ import necessário
import Relatorios from './Relatorios'
import Relatorios1turno from './Relatorio1turno'
import Relatorios2turno from './Relatorio2turno'
import Relatorios3turno from './Relatorio3turno'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/" element={<Home />} />

      <Route path="/dashboard" element={<RequireAuth recurso="dashboard"><Dashboard /></RequireAuth>} />
      <Route path="/turnos" element={<RequireAuth recurso="turnos"><Turnos /></RequireAuth>} />
      <Route path="/teares" element={<RequireAuth recurso="teares"><Teares /></RequireAuth>} />
      <Route path="/motivos" element={<RequireAuth recurso="motivos"><Motivos /></RequireAuth>} />
      <Route path="/usuarios" element={<RequireAuth recurso="usuarios"><Usuarios /></RequireAuth>} />
      <Route path="/relatorios" element={<Relatorios />} />
      <Route path="/Relatorio1turno" element={<Relatorios1turno />} />
      <Route path="/Relatorio2turno" element={<Relatorios2turno />} />
      <Route path="/Relatorio3turno" element={<Relatorios3turno />} />
      <Route path="*" element={<Navigate to="/" />} />
    </Routes>
  )
}
