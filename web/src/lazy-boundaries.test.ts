// 코드 분할 경계 회귀 테스트: 초기 번들에 Plotly/회로도 에디터가 정적으로
// 끌려 들어가는 것을 소스 수준에서 막는다.
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

function source(relative: string): string {
  return readFileSync(new URL(relative, import.meta.url), 'utf8')
}

describe('lazy-loading boundaries', () => {
  it('App은 무거운 모듈을 정적으로 import하지 않는다', () => {
    const app = source('./App.tsx')
    expect(app).not.toMatch(/from '.*PlotlyChart'/)
    expect(app).not.toMatch(/from 'plotly/)
    expect(app).not.toMatch(/from 'katex/)
    expect(app).not.toMatch(/from '.\/tabs\/(?!.*lazy)/) // 탭은 lazy()로만
    expect(app).toMatch(/lazy\(\(\) => import\('.\/tabs\/BodeTab'\)\)/)
    expect(app).toMatch(/lazy\(\(\) => import\('.\/schematic\/SchematicEditor'\)\)/)
    expect(app).toMatch(/<Suspense/)
  })

  it('Plotly는 그래프 탭 모듈에서만 import된다', () => {
    expect(source('./tabs/BodeTab.tsx')).toMatch(/from '..\/components\/PlotlyChart'/)
    expect(source('./tabs/ResponseTab.tsx')).toMatch(/from '..\/components\/PlotlyChart'/)
    for (const light of ['SummaryTab', 'MnaTab', 'SimplifyTab', 'LatexTab', 'VerifyTab']) {
      expect(source(`./tabs/${light}.tsx`)).not.toMatch(/Plotly/)
    }
  })

  it('회로도 에디터는 lazy 로드를 위해 default export를 유지한다', () => {
    expect(source('./schematic/SchematicEditor.tsx')).toMatch(/export default function/)
  })
})
