import { describe, expect, it } from 'vitest'
import { compileSchematic, junctionPoints } from './compile'
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

describe('단락 검출', () => {
  it('부품 양 단자를 잇는 배선은 단락 오류를 낸다', () => {
    const schematic = rcSchematic()
    // R1(0,0)-(4,0)의 두 단자를 위로 우회해 직접 연결
    schematic.wires.push(
      { x1: 0, y1: 0, x2: 0, y2: -2 },
      { x1: 0, y1: -2, x2: 4, y2: -2 },
      { x1: 4, y1: -2, x2: 4, y2: 0 },
    )
    const result = compileSchematic(schematic)
    expect(result.netlist).toBeUndefined()
    expect(result.errors.some((error) => error.includes('단락'))).toBe(true)
  })
})

describe('junctionPoints', () => {
  const empty = (): Schematic => ({ parts: [], wires: [], grounds: [], probe: null })

  it('T 분기(배선 내부에 다른 배선 끝점)에 접점을 찍는다', () => {
    const schematic = empty()
    schematic.wires = [
      { x1: 0, y1: 0, x2: 4, y2: 0 },
      { x1: 2, y1: 0, x2: 2, y2: 2 },
    ]
    expect(junctionPoints(schematic)).toEqual([{ x: 2, y: 0 }])
  })

  it('배선 내부에 놓인 부품 단자도 접점이다', () => {
    const schematic = empty()
    schematic.wires = [{ x1: 0, y1: 2, x2: 8, y2: 2 }]
    schematic.parts = [
      part({ id: 'p', kind: 'R', name: 'R1', value: '1k', x: 0, y: 2 }),
      // R1의 두 번째 단자 (4,2)가 배선 내부에 얹힘
    ]
    expect(junctionPoints(schematic)).toEqual([{ x: 4, y: 2 }])
  })

  it('단순 L자 코너나 끝점 접속은 접점이 아니다', () => {
    const schematic = empty()
    schematic.wires = [
      { x1: 0, y1: 0, x2: 4, y2: 0 },
      { x1: 4, y1: 0, x2: 4, y2: 4 },
    ]
    expect(junctionPoints(schematic)).toEqual([])
  })
})
