import { useEffect, useRef } from 'react'
import Plotly from 'plotly.js-dist-min'

interface Props {
  data: unknown[]
  layout?: Record<string, unknown>
  height?: number
}

export function PlotlyChart({ data, layout = {}, height = 340 }: Props) {
  const container = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const element = container.current
    if (!element) return
    Plotly.newPlot(
      element,
      data,
      { margin: { t: 24, r: 16 }, ...layout },
      { responsive: true, displaylogo: false },
    )
    return () => Plotly.purge(element)
  }, [data, layout])

  return <div ref={container} style={{ width: '100%', height }} />
}
