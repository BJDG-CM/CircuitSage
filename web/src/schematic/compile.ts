// 회로도 → netlist 컴파일 (M6, 설계 §6): 엔진 입장에서는 입력 경로가
// 하나 늘어날 뿐이다. 격자 좌표 위 부품 단자·배선을 union-find로 묶어
// 노드를 판별하고, 접지 마크가 속한 net은 0이 된다.

export type PartKind = 'R' | 'L' | 'C' | 'V' | 'I'

export interface Part {
  id: string
  kind: PartKind
  name: string
  value: string
  ic?: string
  x: number // 첫 단자의 격자 좌표
  y: number
  vertical: boolean
}

export interface Wire {
  x1: number
  y1: number
  x2: number
  y2: number
}

export interface Point {
  x: number
  y: number
}

export interface Schematic {
  parts: Part[]
  wires: Wire[]
  grounds: Point[]
  probe: Point | null
}

export interface CompileResult {
  netlist?: string
  errors: string[]
}

export const PART_LENGTH = 4

export function terminals(part: Part): [Point, Point] {
  const first = { x: part.x, y: part.y }
  const second = part.vertical
    ? { x: part.x, y: part.y + PART_LENGTH }
    : { x: part.x + PART_LENGTH, y: part.y }
  return [first, second]
}

class UnionFind {
  private parent = new Map<string, string>()

  find(key: string): string {
    const stored = this.parent.get(key)
    if (stored === undefined || stored === key) {
      this.parent.set(key, key)
      return key
    }
    const root = this.find(stored)
    this.parent.set(key, root)
    return root
  }

  union(a: string, b: string): void {
    const rootA = this.find(a)
    const rootB = this.find(b)
    if (rootA !== rootB) this.parent.set(rootA, rootB)
  }
}

const pointKey = (x: number, y: number) => `${x},${y}`

// 배선 위 모든 격자점을 같은 net으로 — T 분기(선 중간 접속)를 지원한다
function wireLatticeKeys(wire: Wire): string[] {
  const keys: string[] = []
  if (wire.x1 === wire.x2) {
    const [low, high] = [Math.min(wire.y1, wire.y2), Math.max(wire.y1, wire.y2)]
    for (let y = low; y <= high; y++) keys.push(pointKey(wire.x1, y))
  } else if (wire.y1 === wire.y2) {
    const [low, high] = [Math.min(wire.x1, wire.x2), Math.max(wire.x1, wire.x2)]
    for (let x = low; x <= high; x++) keys.push(pointKey(x, wire.y1))
  } else {
    keys.push(pointKey(wire.x1, wire.y1), pointKey(wire.x2, wire.y2))
  }
  return keys
}

// 전기적으로 3갈래 이상이 만나는 격자점 — 캔버스에 접점(junction dot)을
// 그리기 위한 계산. 배선 내부 통과는 두 방향(+2), 끝점/단자는 +1로 센다.
export function junctionPoints(schematic: Schematic): Point[] {
  const score = new Map<string, number>()
  const bump = (key: string, amount: number) => {
    score.set(key, (score.get(key) ?? 0) + amount)
  }
  for (const wire of schematic.wires) {
    const keys = wireLatticeKeys(wire)
    keys.forEach((key, index) => {
      bump(key, index === 0 || index === keys.length - 1 ? 1 : 2)
    })
  }
  for (const part of schematic.parts) {
    for (const terminal of terminals(part)) {
      bump(pointKey(terminal.x, terminal.y), 1)
    }
  }
  const points: Point[] = []
  for (const [key, value] of score) {
    if (value >= 3) {
      const [x, y] = key.split(',').map(Number)
      points.push({ x, y })
    }
  }
  return points
}

export function compileSchematic(schematic: Schematic): CompileResult {
  const errors: string[] = []
  if (schematic.parts.length === 0) errors.push('소자가 없습니다.')
  if (schematic.grounds.length === 0) errors.push('접지(GND)를 배치하세요.')
  if (!schematic.parts.some((part) => part.kind === 'V' || part.kind === 'I')) {
    errors.push('독립 전원(V 또는 I)이 하나 이상 필요합니다.')
  }
  if (!schematic.probe) errors.push('출력 프로브(V)를 배치하세요.')

  const seenNames = new Set<string>()
  for (const part of schematic.parts) {
    if (!part.value.trim()) errors.push(`${part.name}: 값이 비어 있습니다.`)
    const upper = part.name.toUpperCase()
    if (seenNames.has(upper)) errors.push(`소자 이름 중복: ${part.name}`)
    seenNames.add(upper)
  }
  if (errors.length > 0) return { errors }

  const nets = new UnionFind()
  for (const wire of schematic.wires) {
    const keys = wireLatticeKeys(wire)
    for (let index = 1; index < keys.length; index++) nets.union(keys[0], keys[index])
  }
  const groundRoots = new Set(
    schematic.grounds.map((ground) => nets.find(pointKey(ground.x, ground.y))),
  )

  const netNames = new Map<string, string>()
  let nextNet = 1
  const netOf = (point: Point): string => {
    const root = nets.find(pointKey(point.x, point.y))
    if (groundRoots.has(root)) return '0'
    let name = netNames.get(root)
    if (name === undefined) {
      name = `n${nextNet++}`
      netNames.set(root, name)
    }
    return name
  }

  // 그리다가 만든 단락(양 단자가 같은 net)을 netlist로 내보내기 전에 잡는다
  const shorted = schematic.parts.filter((part) => {
    const [first, second] = terminals(part)
    return (
      nets.find(pointKey(first.x, first.y)) === nets.find(pointKey(second.x, second.y))
    )
  })
  if (shorted.length > 0) {
    return {
      errors: shorted.map(
        (part) => `${part.name}: 두 단자가 같은 net에 연결되어 있습니다 (배선 단락)`,
      ),
    }
  }

  const lines = ['* CircuitSage 회로도에서 컴파일됨']
  for (const part of schematic.parts) {
    const [first, second] = terminals(part)
    let line = `${part.name} ${netOf(first)} ${netOf(second)} ${part.value.trim()}`
    if (part.ic?.trim() && (part.kind === 'L' || part.kind === 'C')) {
      line += ` IC=${part.ic.trim()}`
    }
    lines.push(line)
  }

  const source =
    schematic.parts.find((part) => part.kind === 'V') ??
    schematic.parts.find((part) => part.kind === 'I')!
  lines.push(`.out V(${netOf(schematic.probe!)}) ${source.name}`)
  lines.push('.end')
  return { netlist: lines.join('\n') + '\n', errors: [] }
}
