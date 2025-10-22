// src/perm.ts
// matriz de permissões (com compatibilidade retroativa dos papéis antigos 1..4)

import React from 'react'
import { Navigate } from 'react-router-dom'

export type Recurso = 'dashboard' | 'turnos' | 'teares' | 'motivos' | 'usuarios' | 'relatorios'

// Mapeamento de papéis NOVOS (1..6)
export const PERMS: Record<number, Set<Recurso>> = {
  1: new Set(['dashboard']),                                      // Líder 1º turno
  2: new Set(['dashboard']),                                      // Líder 2º turno
  3: new Set(['dashboard']),                                      // Líder 3º turno
  4: new Set(['dashboard', 'turnos', 'teares', 'motivos']),       // Processos
  5: new Set(['dashboard', 'relatorios']),                        // Gestor
  6: new Set(['dashboard', 'turnos', 'teares', 'motivos', 'usuarios', 'relatorios']) // TI
}

// Compatibilidade: converte papéis ANTIGOS (1..4) para os NOVOS (1..6)
// Antigo: 1=Líder, 2=Processos, 3=Gestor, 4=TI
function normalizeRole(r: number): number {
  if ([1,2,3,4,5,6].includes(r)) {
    // Se já estiver nos novos valores, retorna direto
    if (r <= 4) {
      // pode ser perfil antigo; aplica mapeamento
      if (r === 1) return 1          // Líder -> Líder 1º
      if (r === 2) return 4          // Processos -> 4
      if (r === 3) return 5          // Gestor -> 5
      if (r === 4) return 6          // TI -> 6
    }
    return r
  }
  return 0
}

export function can(role: number, recurso: Recurso) {
  const nr = normalizeRole(role)
  return PERMS[nr]?.has(recurso) ?? false
}

export function RequireAuth({ recurso, children }: { recurso: Recurso; children: JSX.Element }) {
  try {
    const userStr = localStorage.getItem('user')
    const roleRaw = userStr ? JSON.parse(userStr).role : 0
    const role = normalizeRole(Number(roleRaw))
    if (!can(role, recurso)) return <Navigate to="/" replace />
    return children
  } catch {
    return <Navigate to="/login" replace />
  }
}
