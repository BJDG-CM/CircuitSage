import type { SolveResult } from '../api'

export default function LatexTab({ result }: { result: SolveResult }) {
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
