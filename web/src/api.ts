// src/api.ts
// Helpers de chamadas HTTP com token (Bearer) + endpoints da API

import type { Turno, Tear, Motivo, StatusAtual } from './types'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8001'

// --- Auth header (pega token salvo no localStorage) ---
function authHeaders() {
  const t = localStorage.getItem('token')
  return t ? { Authorization: `Bearer ${t}` } : {}
}

// --- HTTP helpers base ---
export async function get<T = any>(path: string): Promise<T> {
  const r = await fetch(`${API}${path}`, { headers: { ...authHeaders() } })
  if (!r.ok) throw new Error(await r.text().catch(() => `HTTP ${r.status}`))
  return r.json()
}

export async function post<T = any>(path: string, body: any): Promise<T> {
  const r = await fetch(`${API}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
  })
  if (!r.ok) throw new Error(await r.text().catch(() => `HTTP ${r.status}`))
  return r.json()
}

export async function put<T = any>(path: string, body: any): Promise<T> {
  const r = await fetch(`${API}${path}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
  })
  if (!r.ok) throw new Error(await r.text().catch(() => `HTTP ${r.status}`))
  return r.json()
}

export async function del(path: string): Promise<void> {
  const r = await fetch(`${API}${path}`, { method: 'DELETE', headers: { ...authHeaders() } })
  if (!r.ok) throw new Error(await r.text().catch(() => `HTTP ${r.status}`))
}

// --- Login / sessão ---
export async function login(nome: string, senha: string) {
  const r = await fetch(`${API}/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ nome, senha }),
  })
  if (!r.ok) throw new Error(await r.text().catch(() => `HTTP ${r.status}`))
  return r.json() as Promise<{ token: string; user: { cod: number; nome: string; role: number } }>
}

export async function me() {
  return get('/me')
}

// --- Dashboard / Status ---
export async function getStatusTeares(): Promise<StatusAtual[]> {
  return get<StatusAtual[]>('/status-teares')
}

// --- Turnos ---
export async function listTurnos(): Promise<Turno[]> {
  return get<Turno[]>('/turnos')
}
export async function saveTurno(t: Turno): Promise<Turno> {
  return post<Turno>('/turnos', t)
}
export async function deleteTurno(dia_semana: number, turno: number): Promise<void> {
  return del(`/turnos/${dia_semana}/${turno}`)
}

// --- Teares ---
export async function listTeares(): Promise<Tear[]> {
  return get<Tear[]>('/teares')
}
export async function createTear(nome?: string): Promise<Tear> {
  // backend aceita nome por query param; se não enviar, gera automaticamente (tearXX)
  const url = nome ? `/teares?nome=${encodeURIComponent(nome)}` : '/teares'
  const r = await fetch(`${API}${url}`, { method: 'POST', headers: { ...authHeaders() } })
  if (!r.ok) throw new Error(await r.text().catch(() => `HTTP ${r.status}`))
  return r.json()
}
export async function renameTear(codigo: number, novo_nome: string): Promise<Tear> {
  const url = `/teares/${codigo}?${new URLSearchParams({ novo_nome }).toString()}`
  const r = await fetch(`${API}${url}`, { method: 'PUT', headers: { ...authHeaders() } })
  if (!r.ok) throw new Error(await r.text().catch(() => `HTTP ${r.status}`))
  return r.json()
}
export async function deleteTearApi(codigo: number): Promise<void> {
  return del(`/teares/${codigo}`)
}

// --- Motivos ---
export async function listMotivos(): Promise<Motivo[]> {
  return get<Motivo[]>('/motivos')
}
export async function saveMotivo(m: Motivo): Promise<Motivo> {
  return post<Motivo>('/motivos', m)
}
export async function deleteMotivo(codigo: number): Promise<void> {
  return del(`/motivos/${codigo}`)
}

// --- Registros (Parada / Funcionando) ---
export type NovoRegistro = { tear: number; data_hora: string; motivo?: number }

export async function registrarParada(body: NovoRegistro) {
  return post('/parada', body)
}
export async function registrarFuncionando(body: NovoRegistro) {
  return post('/funcionando', body)
}
