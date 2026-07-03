import type { MnaDelta } from '../api'

export const VERDICT_KO: Record<string, string> = {
  stable: '안정',
  unstable: '불안정',
  marginal: '임계 안정',
  conditional: '조건부 안정',
}

export function deltaTex(delta: MnaDelta): string {
  if (delta.target === 'A') {
    return `A_{${delta.row + 1},${(delta.col ?? 0) + 1}} \\mathrel{+}= ${delta.term_latex}`
  }
  return `z_{${delta.row + 1}} \\mathrel{+}= ${delta.term_latex}`
}
