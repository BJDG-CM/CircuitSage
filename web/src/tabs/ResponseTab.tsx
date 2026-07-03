import type { SolveResult } from '../api'
import { Katex } from '../components/Katex'
import { PlotlyChart } from '../components/PlotlyChart'

export default function ResponseTab({ result }: { result: SolveResult }) {
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
