import { describe, expect, it } from 'vitest'
import { compileSchematic } from './compile'
import type { Part, Schematic } from './compile'

function part(overrides: Partial<Part> & Pick<Part, 'id' | 'kind' | 'name' | 'value' | 'x' | 'y'>): Part {
  return { vertical: false, ...overrides }
}

// V(0,0→0,4 세로) — R(0,0→4,0 가로) — C(4,0→4,4 세로) — 아래쪽 배선으로 귀환
function rcSchematic(): Schematic {
  return {
    parts: [
      part({ id: 'p1', kind: 'V', name: 'Vin', value: 'Vi', x: 0, y: 0, vertical: true }),
      part({ id: 'p2', kind: 'R', name: 'R1', value: 'R', x: 0, y: 0 }),
      part({ id: 'p3', kind: 'C', name: 'C1', value: 'C', x: 4, y: 0, vertical: true }),
    ],
    wires: [{ x1: 0, y1: 4, x2: 4, y2: 4 }],
    grounds: [{ x: 2, y: 4 }],
    probe: { x: 4, y: 0 },
  }
}

describe('compileSchematic', () => {
  it('RC 회로를 netlist로 컴파일한다', () => {
    const result = compileSchematic(rcSchematic())
    expect(result.errors).toEqual([])
    expect(result.netlist).toBe(
      '* CircuitSage 회로도에서 컴파일됨\n' +
        'Vin n1 0 Vi\n' +
        'R1 n1 n2 R\n' +
        'C1 n2 0 C\n' +
        '.out V(n2) Vin\n' +
        '.end\n',
    )
  })

  it('배선 중간점 접속(T 분기)이 같은 net으로 묶인다', () => {
    const schematic = rcSchematic()
    // 접지 마크가 배선 (0,4)-(4,4)의 중간점 (2,4)에 있음 → 이미 T 분기 케이스.
    // 프로브를 배선 중간이 아닌 부품 단자에 두고도 접지 net이 0이면 통과.
    const result = compileSchematic(schematic)
    expect(result.netlist).toContain('Vin n1 0')
    expect(result.netlist).toContain('C1 n2 0')
  })

  it('접지가 없으면 오류를 낸다', () => {
    const schematic = rcSchematic()
    schematic.grounds = []
    const result = compileSchematic(schematic)
    expect(result.errors.some((error) => error.includes('접지'))).toBe(true)
  })

  it('전원이 없으면 오류를 낸다', () => {
    const schematic = rcSchematic()
    schematic.parts = schematic.parts.filter((item) => item.kind !== 'V')
    const result = compileSchematic(schematic)
    expect(result.errors.some((error) => error.includes('전원'))).toBe(true)
  })

  it('IC가 붙은 L/C는 IC= 표기로 나간다', () => {
    const schematic = rcSchematic()
    schematic.parts[2].ic = '5'
    const result = compileSchematic(schematic)
    expect(result.netlist).toContain('C1 n2 0 C IC=5')
  })

  it('이름이 중복되면 오류를 낸다', () => {
    const schematic = rcSchematic()
    schematic.parts[1].name = 'Vin'
    const result = compileSchematic(schematic)
    expect(result.errors.some((error) => error.includes('중복'))).toBe(true)
  })
})
