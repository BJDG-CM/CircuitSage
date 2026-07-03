import { useState } from 'react'
import type { SolveResult } from '../api'
import { PlotlyChart } from '../components/PlotlyChart'

export default function BodeTab({ result }: { result: SolveResult }) {
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
