import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import CodeMirror from '@uiw/react-codemirror'
import { fetchExamples, solve, SolveError } from './api'
import type { SolveResult } from './api'
import { BodeTab, LatexTab, MnaTab, ResponseTab, SummaryTab, VerifyTab } from './tabs'

const DEFAULT_NETLIST = `* RC 1차 저역통과 — H(s) = 1/(1+sRC)
Vin  in  0    Vi
R1   in  out  R
C1   out 0    C
.out V(out) Vin
.end
`

const TABS = [
  { id: 'summary', label: '요약' },
  { id: 'mna', label: 'MNA 유도' },
  { id: 'response', label: '시간응답' },
  { id: 'bode', label: 'Bode' },
  { id: 'latex', label: 'LaTeX 노트' },
  { id: 'verify', label: '검증' },
] as const

type TabId = (typeof TABS)[number]['id']

function parseNumericValues(text: string): Record<string, number> {
  const values: Record<string, number> = {}
  for (const piece of text.split(/[,\n]/)) {
    const trimmed = piece.trim()
    if (!trimmed) continue
    const [key, raw] = trimmed.split('=').map((part) => part.trim())
    const value = Number(raw)
    if (!key || !Number.isFinite(value)) {
      throw new Error(`수치 값 형식 오류: "${trimmed}" (예: R=1000, C=1e-6)`)
    }
    values[key] = value
  }
  return values
}

export default function App() {
  const [netlist, setNetlist] = useState(DEFAULT_NETLIST)
  const [valuesText, setValuesText] = useState('R=1000, C=1e-6')
  const [wantVerify, setWantVerify] = useState(false)
  const [wantLatex, setWantLatex] = useState(false)
  const [tab, setTab] = useState<TabId>('summary')
  const [inputError, setInputError] = useState<string | null>(null)

  const examples = useQuery({ queryKey: ['examples'], queryFn: fetchExamples })

  const mutation = useMutation<SolveResult, Error, void>({
    mutationFn: () => {
      const numericValues = parseNumericValues(valuesText)
      return solve(netlist, {
        numeric_values: numericValues,
        responses: ['impulse', 'step'],
        verify: wantVerify,
        latex: wantLatex,
      })
    },
  })

  const runSolve = () => {
    setInputError(null)
    try {
      parseNumericValues(valuesText)
    } catch (error) {
      setInputError((error as Error).message)
      return
    }
    mutation.mutate()
  }

  const solveError = mutation.error instanceof SolveError ? mutation.error : null
  const genericError =
    mutation.error && !(mutation.error instanceof SolveError) ? mutation.error : null

  return (
    <div className="layout">
      <aside className="editor-pane">
        <h1>CircuitSage</h1>
        <p className="muted">Symbolic MNA 회로 해석기 — netlist를 입력하고 해석하세요.</p>

        <label className="field-label">
          예제
          <select
            defaultValue=""
            onChange={(event) => {
              const example = examples.data?.find((item) => item.name === event.target.value)
              if (example) setNetlist(example.netlist)
            }}
          >
            <option value="" disabled>
              예제 선택…
            </option>
            {(examples.data ?? []).map((example) => (
              <option key={example.name} value={example.name}>
                {example.title}
              </option>
            ))}
          </select>
        </label>

        <CodeMirror
          value={netlist}
          height="260px"
          basicSetup={{ lineNumbers: true, foldGutter: false }}
          onChange={(value) => setNetlist(value)}
        />

        <label className="field-label">
          수치 값 (Bode·검증용, 예: R=1000, C=1e-6)
          <input
            value={valuesText}
            onChange={(event) => setValuesText(event.target.value)}
            placeholder="R=1000, C=1e-6"
          />
        </label>

        <label className="checkbox">
          <input
            type="checkbox"
            checked={wantVerify}
            onChange={(event) => setWantVerify(event.target.checked)}
          />
          ngspice 검증
        </label>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={wantLatex}
            onChange={(event) => setWantLatex(event.target.checked)}
          />
          LaTeX 노트 생성
        </label>

        <button className="solve-button" onClick={runSolve} disabled={mutation.isPending}>
          {mutation.isPending ? '해석 중…' : '해석 실행'}
        </button>

        {inputError && <div className="error-box">{inputError}</div>}
        {solveError && (
          <div className="error-box">
            <strong>{solveError.code}</strong>
            {solveError.lineNo != null && ` (라인 ${solveError.lineNo})`}
            <br />
            {solveError.message}
          </div>
        )}
        {genericError && <div className="error-box">{genericError.message}</div>}
      </aside>

      <main className="result-pane">
        <nav className="tab-bar">
          {TABS.map((item) => (
            <button
              key={item.id}
              className={tab === item.id ? 'tab active' : 'tab'}
              onClick={() => setTab(item.id)}
              disabled={!mutation.data}
            >
              {item.label}
            </button>
          ))}
        </nav>
        <div className="tab-body">
          {!mutation.data && <p className="muted">좌측에서 회로를 해석하면 결과가 표시됩니다.</p>}
          {mutation.data && tab === 'summary' && <SummaryTab result={mutation.data} />}
          {mutation.data && tab === 'mna' && <MnaTab result={mutation.data} />}
          {mutation.data && tab === 'response' && <ResponseTab result={mutation.data} />}
          {mutation.data && tab === 'bode' && <BodeTab result={mutation.data} />}
          {mutation.data && tab === 'latex' && <LatexTab result={mutation.data} />}
          {mutation.data && tab === 'verify' && <VerifyTab result={mutation.data} />}
        </div>
      </main>
    </div>
  )
}
