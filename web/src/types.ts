export type Motivo = { codigo: number; descricao: string }
export type StatusAtual = { tear: number; status: 0 | 1; desde?: string; horas?: number; nome?: string; }
export type NovoRegistro = { tear: number; data_hora: string; motivo?: number }
export type Turno = { turno: number; dia_semana: number; inicio: string; fim: string }
export type Tear = { codigo: number; nome: string }
