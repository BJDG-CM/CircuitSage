import type { SolveResult } from '../api'
import { Katex } from '../components/Katex'

export default function SimplifyTab({ result }: { result: SolveResult }) {
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
