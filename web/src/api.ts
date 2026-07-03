// CircuitSage API 클라이언트 (설계 §5의 응답 형태를 그대로 타입화)

export interface SolveOptions {
  numeric_values?: Record<string, number>
  responses?: string[]
  verify?: boolean
  latex?: boolean
}

export interface RootEntry {
  latex: string
  re?: number
  im?: number
  multiplicity: number
}

export interface RootSetDto {
  complete: boolean
  roots: RootEntry[]
}

export interface MnaDelta {
  target: 'A' | 'z'
  row: number
  col: number | null
  term_latex: string
}

export interface MnaStep {
  component: string
  deltas: MnaDelta[]
}

export interface MnaDto {
  A_latex: string
  z_latex: string
  x_latex: string
  steps: MnaStep[]
  checkpoints: { component: string; A_latex: string }[]
}

export interface StabilityDto {
  verdict: string
  method: string
  conditions_latex: string[]
  routh_table_latex: string | null
  notes: string[]
}

export interface SystemModesDto {
  status: string // "ok" | "static" | "partial" | "unknown"
  note: string
  characteristic_latex: string | null
  modes: RootSetDto | null
  internal_stability: StabilityDto | null
}

export interface ResponseEntry {
  latex: string
  partial_fractions_latex: string
  method: string
  samples?: { t: number[]; y: number[] }
}

export interface BodeDto {
  freq: number[]
  mag_db: number[]
  phase_deg: number[]
  mag_db_asymptotic: number[]
  corners: number[]
}

export interface VerificationReportDto {
  kind: string
  passed: boolean
  max_rel_error: number
  worst_at: number
  points: number
  notes: string[]
}

export interface TransferFunctionDto {
  latex: string
  numerator: string
  denominator: string
  output_node: string
  input_source: string
}

export interface SimplificationStepDto {
  rule: string
  description: string
  latex: string
  removed: string[]
  created: string[]
}

export interface SimplificationDto {
  steps: SimplificationStepDto[]
  final_component_count: number
  verified: boolean | null
}

export interface SolveResult {
  nodes: string[]
  planarity: { planar: boolean }
  mna: MnaDto
  transfer_function: TransferFunctionDto
  poles: RootSetDto
  zeros: RootSetDto
  transfer_stability: StabilityDto
  system_modes?: SystemModesDto
  responses?: Record<string, ResponseEntry>
  bode?: BodeDto
  simplification?: SimplificationDto
  verification?: { passed: boolean; reports: VerificationReportDto[] }
  latex_report?: string
  warnings: string[]
}

export interface Example {
  name: string
  title: string
  netlist: string
}

export interface ApiErrorBody {
  code: string
  message: string
  line_no?: number
}

export class SolveError extends Error {
  code: string
  lineNo?: number

  constructor(body: ApiErrorBody) {
    super(body.message)
    this.code = body.code
    this.lineNo = body.line_no
  }
}

export async function solve(netlist: string, options: SolveOptions): Promise<SolveResult> {
  const response = await fetch('/api/solve', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ netlist, options }),
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new SolveError(
      body?.error ?? { code: `HTTP_${response.status}`, message: response.statusText },
    )
  }
  return response.json()
}

export async function fetchExamples(): Promise<Example[]> {
  const response = await fetch('/api/examples')
  if (!response.ok) throw new Error(`예제 목록 로드 실패 (${response.status})`)
  return response.json()
}

export interface SharedCircuit {
  netlist: string
  options: { numeric_values?: Record<string, number> }
}

export async function createShare(
  netlist: string,
  options: SharedCircuit['options'],
): Promise<string> {
  const response = await fetch('/api/share', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ netlist, options }),
  })
  if (!response.ok) throw new Error(`공유 링크 생성 실패 (${response.status})`)
  const body = await response.json()
  return body.id as string
}

export async function fetchShare(id: string): Promise<SharedCircuit> {
  const response = await fetch(`/api/share/${id}`)
  if (!response.ok) throw new Error(`공유 링크 로드 실패 (${response.status})`)
  return response.json()
}
