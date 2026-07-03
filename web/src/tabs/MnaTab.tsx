import type { SolveResult } from '../api'
import { Katex } from '../components/Katex'
import { deltaTex } from './common'

export default function MnaTab({ result }: { result: SolveResult }) {
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
