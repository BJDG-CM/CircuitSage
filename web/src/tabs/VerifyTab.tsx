import type { SolveResult } from '../api'

export default function VerifyTab({ result }: { result: SolveResult }) {
  const verification = result.verification
  if (!verification) {
    return <p>검증 결과가 없습니다 — 좌측에서 "ngspice 검증"을 켜세요 (선택 기능).</p>
  }
  if (verification.status === 'unavailable') {
    return (
      <p>
        서버에 ngspice가 설치되어 있지 않아 교차 검증을 사용할 수 없습니다. 검증은
        선택 기능이며, 심볼릭 해석 결과에는 영향이 없습니다.
      </p>
    )
  }
  if (verification.status === 'error') {
    return (
      <div>
        <p>검증 실행에 실패했습니다:</p>
        <pre className="tex-preview">{verification.detail}</pre>
      </div>
    )
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
