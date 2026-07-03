import { useState } from 'react'
import type { MnaDelta, SolveResult } from './api'
import { Katex } from './components/Katex'
import { PlotlyChart } from './components/PlotlyChart'

const VERDICT_KO: Record<string, string> = {
  stable: '안정',
  unstable: '불안정',
  marginal: '임계 안정',
  conditional: '조건부 안정',
}

function deltaTex(delta: MnaDelta): string {
  if (delta.target === 'A') {
    return `A_{${delta.row + 1},${(delta.col ?? 0) + 1}} \\mathrel{+}= ${delta.term_latex}`
  }
  return `z_{${delta.row + 1}} \\mathrel{+}= ${delta.term_latex}`
}

export function SummaryTab({ result }: { result: SolveResult }) {
  const tf = result.transfer_function
  const stability = result.transfer_stability
  const systemModes = result.system_modes
  return (
    <div>
      <h3>전달함수</h3>
      <Katex
        block
        tex={`H(s) = \\frac{V_{${tf.output_node}}(s)}{${tf.input_source}(s)} = ${tf.latex}`}
      />
      <h3>전달함수 극점 / 영점</h3>
      {result.poles.roots.length === 0 && (
        <p>
          전달함수 극점 없음
          {systemModes && systemModes.modes && systemModes.modes.roots.length > 0
            ? ' — 소거된 내부 모드가 존재합니다 (아래 시스템 내부 모드 참고)'
            : ' (동특성 없음)'}
        </p>
      )}
      <ul>
        {result.poles.roots.map((root, index) => (
          <li key={index}>
            <Katex tex={`p = ${root.latex}`} />
            {root.multiplicity > 1 && ` (중복도 ${root.multiplicity})`}
          </li>
        ))}
      </ul>
      {result.zeros.roots.length > 0 && (
        <ul>
          {result.zeros.roots.map((root, index) => (
            <li key={index}>
              <Katex tex={`z = ${root.latex}`} />
              {root.multiplicity > 1 && ` (중복도 ${root.multiplicity})`}
            </li>
          ))}
        </ul>
      )}
      <h3>전달함수 안정성</h3>
      <p className="muted">
        소거 후 전달함수 분모 기준 — 내부 모드는 아래에서 별도 판정합니다.
      </p>
      <p>
        <strong>{VERDICT_KO[stability.verdict] ?? stability.verdict}</strong>{' '}
        ({stability.method === 'routh' ? 'Routh–Hurwitz' : '수치 극점'})
      </p>
      {stability.conditions_latex.length > 0 && (
        <>
          <p>안정 조건:</p>
          <ul>
            {stability.conditions_latex.map((condition, index) => (
              <li key={index}>
                <Katex tex={condition} />
              </li>
            ))}
          </ul>
        </>
      )}
      {stability.routh_table_latex && (
        <>
          <p>Routh 표:</p>
          <Katex block tex={stability.routh_table_latex} />
        </>
      )}
      {systemModes && (
        <>
          <h3>시스템 내부 모드</h3>
          <p className="muted">
            MNA 행렬식 det A(s)에서 독립적으로 유도 — 전달함수에서 소거된 모드도
            포함합니다.
          </p>
          {systemModes.characteristic_latex && systemModes.status !== 'static' && (
            <Katex block tex={`${systemModes.characteristic_latex} = 0`} />
          )}
          {systemModes.modes && systemModes.modes.roots.length > 0 ? (
            <ul>
              {systemModes.modes.roots.map((root, index) => (
                <li key={index}>
                  <Katex tex={`s = ${root.latex}`} />
                  {root.multiplicity > 1 && ` (중복도 ${root.multiplicity})`}
                </li>
              ))}
            </ul>
          ) : (
            <p>
              {systemModes.status === 'static'
                ? '동적 내부 모드 없음'
                : '이 위상에서는 내부 모드를 신뢰성 있게 추출할 수 없습니다.'}
            </p>
          )}
          {systemModes.internal_stability && (
            <p>
              내부 안정성:{' '}
              <strong>
                {VERDICT_KO[systemModes.internal_stability.verdict] ??
                  systemModes.internal_stability.verdict}
              </strong>
            </p>
          )}
          <p className="muted">{systemModes.note}</p>
        </>
      )}
      {result.warnings.length > 0 && (
        <div className="warnings">
          {result.warnings.map((warning, index) => (
            <p key={index}>⚠ {warning}</p>
          ))}
        </div>
      )}
    </div>
  )
}

export function MnaTab({ result }: { result: SolveResult }) {
  const mna = result.mna
  return (
    <div>
      <h3>미지수 벡터</h3>
      <Katex block tex={`x = ${mna.x_latex}`} />
      <h3>소자별 스탬프 (델타 기록)</h3>
      <ul>
        {mna.steps.map((step) => (
          <li key={step.component}>
            <strong>{step.component}</strong>:{' '}
            {step.deltas.length === 0
              ? '(접지 기준행으로 소거됨)'
              : step.deltas.map((delta, index) => (
                  <span key={index}>
                    <Katex tex={deltaTex(delta)} />
                    {index < step.deltas.length - 1 && ', '}
                  </span>
                ))}
          </li>
        ))}
      </ul>
      <h3>체크포인트 행렬</h3>
      {mna.checkpoints.map((checkpoint) => (
        <div key={checkpoint.component}>
          <p>{checkpoint.component} 스탬프까지 적용한 뒤:</p>
          <Katex block tex={`A = ${checkpoint.A_latex}`} />
        </div>
      ))}
      <h3>우변</h3>
      <Katex block tex={`z = ${mna.z_latex}`} />
    </div>
  )
}

export function ResponseTab({ result }: { result: SolveResult }) {
  const responses = result.responses ?? {}
  const kinds = Object.keys(responses)
  if (kinds.length === 0) return <p>시간응답이 요청되지 않았거나 계산에 실패했습니다.</p>
  return (
    <div>
      {kinds.map((kind) => {
        const entry = responses[kind]
        return (
          <div key={kind}>
            <h3>{kind === 'impulse' ? '임펄스 응답 h(t)' : '스텝 응답 y(t)'}</h3>
            <p className="muted">부분분수 분해:</p>
            <Katex block tex={entry.partial_fractions_latex} />
            <Katex block tex={entry.latex} />
            <p className="muted">방법: {entry.method === 'table' ? '자체 변환표' : 'SymPy fallback'}</p>
            {entry.samples && (
              <PlotlyChart
                data={[
                  {
                    x: entry.samples.t,
                    y: entry.samples.y,
                    type: 'scatter',
                    mode: 'lines',
                    name: kind,
                  },
                ]}
                layout={{ xaxis: { title: { text: 't (s)' } } }}
              />
            )}
          </div>
        )
      })}
    </div>
  )
}

export function BodeTab({ result }: { result: SolveResult }) {
  const [showAsymptote, setShowAsymptote] = useState(true)
  const bode = result.bode
  if (!bode) {
    return <p>Bode 데이터가 없습니다 — 기호 값 회로는 좌측에서 수치 값을 지정하세요.</p>
  }
  const magnitudeTraces: unknown[] = [
    { x: bode.freq, y: bode.mag_db, type: 'scatter', mode: 'lines', name: '|H| (dB)' },
  ]
  if (showAsymptote) {
    magnitudeTraces.push({
      x: bode.freq,
      y: bode.mag_db_asymptotic,
      type: 'scatter',
      mode: 'lines',
      name: '꺾은선 근사',
      line: { dash: 'dash' },
    })
  }
  return (
    <div>
      <label className="checkbox">
        <input
          type="checkbox"
          checked={showAsymptote}
          onChange={(event) => setShowAsymptote(event.target.checked)}
        />
        점근선(asymptote) 표시
      </label>
      <PlotlyChart
        data={magnitudeTraces}
        layout={{
          xaxis: { type: 'log', title: { text: 'ω (rad/s)' } },
          yaxis: { title: { text: 'dB' } },
        }}
      />
      <PlotlyChart
        data={[
          { x: bode.freq, y: bode.phase_deg, type: 'scatter', mode: 'lines', name: '위상 (°)' },
        ]}
        layout={{
          xaxis: { type: 'log', title: { text: 'ω (rad/s)' } },
          yaxis: { title: { text: 'deg' } },
        }}
      />
      {bode.corners.length > 0 && (
        <p className="muted">Corner 주파수: {bode.corners.map((c) => c.toPrecision(4)).join(', ')} rad/s</p>
      )}
    </div>
  )
}

export function LatexTab({ result }: { result: SolveResult }) {
  const tex = result.latex_report
  if (!tex) return <p>좌측에서 "LaTeX 노트 생성"을 켜고 다시 해석하세요.</p>
  const download = () => {
    const blob = new Blob([tex], { type: 'text/x-tex' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = 'circuitsage-note.tex'
    anchor.click()
    URL.revokeObjectURL(url)
  }
  return (
    <div>
      <button onClick={download}>.tex 다운로드</button>
      <pre className="tex-preview">{tex}</pre>
    </div>
  )
}

export function SimplifyTab({ result }: { result: SolveResult }) {
  const simplification = result.simplification
  if (!simplification) return <p>단순화 정보가 없습니다.</p>
  if (simplification.steps.length === 0) {
    return (
      <p>
        적용 가능한 직렬/병렬/전원 변환이 없습니다 — 브리지처럼 단순화로 환원되지
        않는 회로입니다 (해석은 MNA로 수행되므로 결과에는 영향이 없습니다).
      </p>
    )
  }
  return (
    <div>
      <ol>
        {simplification.steps.map((step, index) => (
          <li key={index}>
            <p>
              <strong>[{step.rule}]</strong> {step.description}
            </p>
            <Katex block tex={step.latex} />
          </li>
        ))}
      </ol>
      <p className="muted">최종 소자 수: {simplification.final_component_count}</p>
      {simplification.verified === true && <p>✅ 단순화 전후 H(s) 일치 (MNA 자체 검증)</p>}
      {simplification.verified === false && (
        <p>❌ 단순화 전후 H(s) 불일치 — 버그 가능성, 결과는 MNA 기준입니다.</p>
      )}
    </div>
  )
}

export function VerifyTab({ result }: { result: SolveResult }) {
  const verification = result.verification
  if (!verification) {
    return <p>검증 결과가 없습니다 — 좌측에서 "ngspice 검증"을 켜세요 (서버에 ngspice 필요).</p>
  }
  return (
    <div>
      <h3>{verification.passed ? '✅ 전체 통과' : '❌ 실패'}</h3>
      <table>
        <thead>
          <tr>
            <th>해석</th>
            <th>판정</th>
            <th>최대 상대오차</th>
            <th>위치</th>
            <th>표본</th>
          </tr>
        </thead>
        <tbody>
          {verification.reports.map((report) => (
            <tr key={report.kind}>
              <td>{report.kind}</td>
              <td>{report.passed ? '통과' : '실패'}</td>
              <td>{report.max_rel_error.toExponential(2)}</td>
              <td>{report.worst_at.toPrecision(4)}</td>
              <td>{report.points}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
