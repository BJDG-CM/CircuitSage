import { useRef, useState } from 'react'
import { compileSchematic, terminals } from './compile'
import type { Part, PartKind, Point, Schematic, Wire } from './compile'

const GRID = 20
const PAD = 10
const COLS = 30
const ROWS = 18

type Tool = 'select' | PartKind | 'wire' | 'ground' | 'probe' | 'delete'

const PART_TOOLS: { kind: PartKind; label: string }[] = [
  { kind: 'R', label: '저항' },
  { kind: 'L', label: '인덕터' },
  { kind: 'C', label: '커패시터' },
  { kind: 'V', label: '전압원' },
  { kind: 'I', label: '전류원' },
]

const DEFAULT_VALUES: Record<PartKind, string> = {
  R: '1k',
  L: '1m',
  C: '1u',
  V: 'Vi',
  I: 'Ii',
}

const toPx = (grid: number) => grid * GRID + PAD

export default function SchematicEditor({
  onCompile,
}: {
  onCompile: (netlist: string) => void
}) {
  const [schematic, setSchematic] = useState<Schematic>({
    parts: [],
    wires: [],
    grounds: [],
    probe: null,
  })
  const [tool, setTool] = useState<Tool>('select')
  const [wireStart, setWireStart] = useState<Point | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [errors, setErrors] = useState<string[]>([])
  const svgRef = useRef<SVGSVGElement>(null)
  const idCounter = useRef(0)

  const selected = schematic.parts.find((part) => part.id === selectedId) ?? null

  const nextName = (kind: PartKind): string => {
    let index = 1
    const taken = new Set(schematic.parts.map((part) => part.name.toUpperCase()))
    while (taken.has(`${kind}${index}`)) index++
    return `${kind}${index}`
  }

  const gridPoint = (event: React.MouseEvent): Point => {
    const rect = svgRef.current!.getBoundingClientRect()
    const x = Math.round((event.clientX - rect.left - PAD) / GRID)
    const y = Math.round((event.clientY - rect.top - PAD) / GRID)
    return { x: Math.max(0, Math.min(COLS, x)), y: Math.max(0, Math.min(ROWS, y)) }
  }

  const canvasClick = (event: React.MouseEvent) => {
    const point = gridPoint(event)
    if (tool === 'wire') {
      if (!wireStart) {
        setWireStart(point)
      } else {
        const wires: Wire[] = []
        if (wireStart.x !== point.x) {
          wires.push({ x1: wireStart.x, y1: wireStart.y, x2: point.x, y2: wireStart.y })
        }
        if (wireStart.y !== point.y) {
          wires.push({ x1: point.x, y1: wireStart.y, x2: point.x, y2: point.y })
        }
        if (wires.length > 0) {
          setSchematic((prev) => ({ ...prev, wires: [...prev.wires, ...wires] }))
        }
        setWireStart(null)
      }
      return
    }
    if (tool === 'ground') {
      setSchematic((prev) => ({ ...prev, grounds: [...prev.grounds, point] }))
      return
    }
    if (tool === 'probe') {
      setSchematic((prev) => ({ ...prev, probe: point }))
      return
    }
    const partTool = PART_TOOLS.find((item) => item.kind === tool)
    if (partTool) {
      const part: Part = {
        id: `part${idCounter.current++}`,
        kind: partTool.kind,
        name: nextName(partTool.kind),
        value: DEFAULT_VALUES[partTool.kind],
        x: point.x,
        y: point.y,
        vertical: false,
      }
      setSchematic((prev) => ({ ...prev, parts: [...prev.parts, part] }))
      setSelectedId(part.id)
    }
  }

  const partClick = (event: React.MouseEvent, part: Part) => {
    event.stopPropagation()
    if (tool === 'delete') {
      setSchematic((prev) => ({ ...prev, parts: prev.parts.filter((item) => item.id !== part.id) }))
      if (selectedId === part.id) setSelectedId(null)
    } else {
      setSelectedId(part.id)
    }
  }

  const wireClick = (event: React.MouseEvent, index: number) => {
    if (tool !== 'delete') return
    event.stopPropagation()
    setSchematic((prev) => ({ ...prev, wires: prev.wires.filter((_, i) => i !== index) }))
  }

  const groundClick = (event: React.MouseEvent, index: number) => {
    if (tool !== 'delete') return
    event.stopPropagation()
    setSchematic((prev) => ({ ...prev, grounds: prev.grounds.filter((_, i) => i !== index) }))
  }

  const updateSelected = (changes: Partial<Part>) => {
    if (!selected) return
    setSchematic((prev) => ({
      ...prev,
      parts: prev.parts.map((part) => (part.id === selected.id ? { ...part, ...changes } : part)),
    }))
  }

  const compile = () => {
    const result = compileSchematic(schematic)
    setErrors(result.errors)
    if (result.netlist) onCompile(result.netlist)
  }

  return (
    <div className="schematic">
      <div className="tool-bar">
        <button className={tool === 'select' ? 'active' : ''} onClick={() => setTool('select')}>
          선택
        </button>
        {PART_TOOLS.map((item) => (
          <button
            key={item.kind}
            className={tool === item.kind ? 'active' : ''}
            onClick={() => setTool(item.kind)}
          >
            {item.label}
          </button>
        ))}
        <button className={tool === 'wire' ? 'active' : ''} onClick={() => { setTool('wire'); setWireStart(null) }}>
          배선
        </button>
        <button className={tool === 'ground' ? 'active' : ''} onClick={() => setTool('ground')}>
          접지
        </button>
        <button className={tool === 'probe' ? 'active' : ''} onClick={() => setTool('probe')}>
          출력 프로브
        </button>
        <button className={tool === 'delete' ? 'active' : ''} onClick={() => setTool('delete')}>
          삭제
        </button>
      </div>

      <svg
        ref={svgRef}
        width={COLS * GRID + PAD * 2}
        height={ROWS * GRID + PAD * 2}
        className="schematic-canvas"
        onClick={canvasClick}
      >
        <defs>
          <pattern id="dots" width={GRID} height={GRID} patternUnits="userSpaceOnUse" x={PAD} y={PAD}>
            <circle cx={0} cy={0} r={1} fill="#c9c7d0" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#dots)" />

        {schematic.wires.map((wire, index) => (
          <line
            key={`w${index}`}
            x1={toPx(wire.x1)}
            y1={toPx(wire.y1)}
            x2={toPx(wire.x2)}
            y2={toPx(wire.y2)}
            stroke="#2b2b33"
            strokeWidth={2}
            onClick={(event) => wireClick(event, index)}
          />
        ))}

        {schematic.parts.map((part) => {
          const [first, second] = terminals(part)
          const midX = (toPx(first.x) + toPx(second.x)) / 2
          const midY = (toPx(first.y) + toPx(second.y)) / 2
          const isSelected = part.id === selectedId
          return (
            <g key={part.id} onClick={(event) => partClick(event, part)} style={{ cursor: 'pointer' }}>
              <line
                x1={toPx(first.x)}
                y1={toPx(first.y)}
                x2={toPx(second.x)}
                y2={toPx(second.y)}
                stroke="#2b2b33"
                strokeWidth={2}
              />
              <rect
                x={midX - (part.vertical ? 11 : 19)}
                y={midY - (part.vertical ? 19 : 11)}
                width={part.vertical ? 22 : 38}
                height={part.vertical ? 38 : 22}
                rx={4}
                fill={isSelected ? '#eef2ff' : 'white'}
                stroke={isSelected ? '#4b5cc4' : '#2b2b33'}
                strokeWidth={isSelected ? 2 : 1.5}
              />
              <text x={midX} y={midY + 4} textAnchor="middle" fontSize={12} fontWeight={600}>
                {part.kind}
              </text>
              <text
                x={part.vertical ? midX + 16 : midX}
                y={part.vertical ? midY : midY + (part.kind === 'V' || part.kind === 'I' ? -16 : 24)}
                textAnchor={part.vertical ? 'start' : 'middle'}
                fontSize={10}
                fill="#6b6375"
              >
                {part.name}={part.value}
              </text>
              <circle cx={toPx(first.x)} cy={toPx(first.y)} r={3} fill="#4b5cc4" />
              <circle cx={toPx(second.x)} cy={toPx(second.y)} r={3} fill="#2b2b33" />
            </g>
          )
        })}

        {schematic.grounds.map((ground, index) => (
          <g key={`g${index}`} onClick={(event) => groundClick(event, index)}>
            <line x1={toPx(ground.x)} y1={toPx(ground.y)} x2={toPx(ground.x)} y2={toPx(ground.y) + 8} stroke="#2b2b33" strokeWidth={2} />
            <line x1={toPx(ground.x) - 8} y1={toPx(ground.y) + 8} x2={toPx(ground.x) + 8} y2={toPx(ground.y) + 8} stroke="#2b2b33" strokeWidth={2} />
            <line x1={toPx(ground.x) - 5} y1={toPx(ground.y) + 12} x2={toPx(ground.x) + 5} y2={toPx(ground.y) + 12} stroke="#2b2b33" strokeWidth={2} />
            <line x1={toPx(ground.x) - 2} y1={toPx(ground.y) + 16} x2={toPx(ground.x) + 2} y2={toPx(ground.y) + 16} stroke="#2b2b33" strokeWidth={2} />
          </g>
        ))}

        {schematic.probe && (
          <g>
            <circle cx={toPx(schematic.probe.x)} cy={toPx(schematic.probe.y)} r={8} fill="none" stroke="#c2410c" strokeWidth={2} />
            <text x={toPx(schematic.probe.x)} y={toPx(schematic.probe.y) - 12} textAnchor="middle" fontSize={11} fill="#c2410c">
              V(out)
            </text>
          </g>
        )}

        {wireStart && (
          <circle cx={toPx(wireStart.x)} cy={toPx(wireStart.y)} r={5} fill="#4b5cc4" opacity={0.6} />
        )}
      </svg>

      {selected && (
        <div className="part-panel">
          <label>
            이름
            <input value={selected.name} onChange={(event) => updateSelected({ name: event.target.value })} />
          </label>
          <label>
            값
            <input value={selected.value} onChange={(event) => updateSelected({ value: event.target.value })} />
          </label>
          {(selected.kind === 'L' || selected.kind === 'C') && (
            <label>
              IC
              <input
                value={selected.ic ?? ''}
                placeholder={selected.kind === 'L' ? 'i(0⁻)' : 'v(0⁻)'}
                onChange={(event) => updateSelected({ ic: event.target.value })}
              />
            </label>
          )}
          <button onClick={() => updateSelected({ vertical: !selected.vertical })}>회전</button>
        </div>
      )}

      <button className="solve-button" onClick={compile}>
        netlist로 컴파일
      </button>
      {errors.length > 0 && (
        <div className="error-box">
          {errors.map((error, index) => (
            <div key={index}>• {error}</div>
          ))}
        </div>
      )}
      <p className="muted">
        부품 도구로 캔버스를 클릭해 배치하고(첫 단자 기준, 길이 4칸), 배선 도구로 두 점을
        클릭해 연결하세요. 접지와 출력 프로브는 필수입니다.
      </p>
    </div>
  )
}
