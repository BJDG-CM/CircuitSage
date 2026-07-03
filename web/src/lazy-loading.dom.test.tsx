// @vitest-environment jsdom
// DOM 수준 lazy 경계 테스트: 실제 렌더 트리에서 Plotly 모듈이
// 그래프 탭을 열기 전까지 로드되지 않는 것을 검증한다.
import { cleanup, render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'

const state = vi.hoisted(() => ({ plotlyLoaded: false }))

vi.mock('plotly.js-dist-min', () => {
  state.plotlyLoaded = true
  return { default: { newPlot: vi.fn(async () => {}), purge: vi.fn() } }
})

// CodeMirror는 jsdom에 불필요한 DOM API를 요구하므로 얇게 대체한다
vi.mock('@uiw/react-codemirror', () => ({ default: () => null }))

const SOLVE_RESULT = {
  nodes: ['in', '0', 'out'],
  planarity: { planar: true },
  mna: { A_latex: 'A', z_latex: 'z', x_latex: 'x', steps: [], checkpoints: [] },
  transfer_function: {
    latex: '\\frac{1}{s + 1}',
    numerator: '1',
    denominator: 's + 1',
    output_node: 'out',
    input_source: 'Vin',
  },
  poles: { complete: true, roots: [{ latex: '-1', multiplicity: 1, re: -1, im: 0 }] },
  zeros: { complete: true, roots: [] },
  transfer_stability: {
    verdict: 'stable',
    method: 'numeric',
    conditions_latex: [],
    routh_table_latex: null,
    notes: [],
  },
  system_modes: {
    status: 'ok',
    note: '',
    characteristic_latex: 's + 1',
    modes: { complete: true, roots: [{ latex: '-1', multiplicity: 1 }] },
    internal_stability: {
      verdict: 'stable',
      method: 'numeric',
      conditions_latex: [],
      routh_table_latex: null,
      notes: [],
    },
  },
  responses: {},
  bode: {
    freq: [1, 10, 100],
    mag_db: [0, -1, -10],
    phase_deg: [0, -10, -45],
    mag_db_asymptotic: [0, -1, -10],
    corners: [1],
  },
  simplification: { steps: [], final_component_count: 3, verified: null },
  warnings: [],
}

function jsonResponse(data: unknown) {
  return { ok: true, status: 200, json: async () => data } as Response
}

function renderApp() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>,
  )
}

afterEach(cleanup)

beforeEach(() => {
  state.plotlyLoaded = false
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/api/examples')) return jsonResponse([])
      if (url.includes('/api/solve')) return jsonResponse(SOLVE_RESULT)
      throw new Error(`unexpected fetch: ${url}`)
    }),
  )
})

describe('lazy loading in the rendered app', () => {
  it('초기 화면과 요약 탭까지는 Plotly를 로드하지 않는다', async () => {
    renderApp()
    fireEvent.click(await screen.findByText('해석 실행'))
    // lazy SummaryTab이 로드되어 전달함수 섹션이 보일 때까지 대기
    await screen.findByText('전달함수')
    expect(state.plotlyLoaded).toBe(false)
  })

  it('Bode 탭을 열면 그때 Plotly가 로드된다', async () => {
    renderApp()
    fireEvent.click(await screen.findByText('해석 실행'))
    await screen.findByText('전달함수')

    fireEvent.click(screen.getByText('Bode'))
    await waitFor(() => expect(state.plotlyLoaded).toBe(true))
    await screen.findByText(/점근선/)
  })

  it('요약 탭이 소거된 내부 모드 안내를 렌더링한다', async () => {
    renderApp()
    fireEvent.click(await screen.findByText('해석 실행'))
    await screen.findByText('시스템 내부 모드')
    expect(screen.getByText(/내부 안정성/)).toBeTruthy()
  })
})
