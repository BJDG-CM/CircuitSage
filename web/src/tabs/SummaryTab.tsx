import type { SolveResult } from '../api'
import { Katex } from '../components/Katex'
import { VERDICT_KO } from './common'

export default function SummaryTab({ result }: { result: SolveResult }) {
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
