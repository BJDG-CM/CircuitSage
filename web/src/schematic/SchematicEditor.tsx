import { useEffect, useRef, useState } from 'react'
import { compileSchematic, junctionPoints, terminals } from './compile'
import type { CompileResult, Part, PartKind, Point, Schematic, Wire } from './compile'

const GRID = 20
const PAD = 10
const COLS = 30
const ROWS = 18
const PART_PX = 80 // 단자 간 4칸 × 20px

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

function capturePointer(svg: SVGSVGElement | null, pointerId: number) {
  try {
    svg?.setPointerCapture(pointerId)
  } catch {
    // 합성 이벤트 등 비활성 pointerId면 캡처 없이 진행한다
  }
}

// ── 회로 심볼 (로컬 좌표: 단자 (0,0)–(80,0), 가로 기준) ──────────────────
function SymbolBody({ kind }: { kind: PartKind }) {
  const stroke = { stroke: 'currentColor', strokeWidth: 2, fill: 'none' } as const
  switch (kind) {
    case 'R':
      return (
        <polyline
          {...stroke}
          points="0,0 24,0 28,-8 36,8 44,-8 52,8 58,-4 60,0 80,0"
        />
      )
    case 'L':
      return (
        <path
          {...stroke}
          d="M0,0 H20 A7,7 0 0 0 34,0 A7,7 0 0 0 48,0 A7,7 0 0 0 62,0 H80"
        />
      )
    case 'C':
      return (
        <g {...stroke}>
          <path d="M0,0 H36 M44,0 H80" />
          <path d="M36,-11 V11 M44,-11 V11" />
        </g>
      )
    case 'V':
      return (
        <g {...stroke}>
          <path d="M0,0 H28 M52,0 H80" />
          <circle cx={40} cy={0} r={12} />
          <path d="M32,0 H38 M35,-3 V3" strokeWidth={1.6} />
          <path d="M42,0 H48" strokeWidth={1.6} />
        </g>
      )
    case 'I':
      return (
        <g {...stroke}>
          <path d="M0,0 H28 M52,0 H80" />
          <circle cx={40} cy={0} r={12} />
          <path d="M33,0 H44" strokeWidth={1.6} />
          <path d="M44,0 L40,-3.5 M44,0 L40,3.5" strokeWidth={1.6} />
        </g>
      )
  }
}

export default function SchematicEditor({
  onCompile,
  onLiveNetlist,
}: {
  onCompile: (netlist: string) => void
  onLiveNetlist?: (netlist: string | null, errors: string[]) => void
}) {
  const [schematic, setSchematic] = useState<Schematic>({
    parts: [],
    wires: [],
    grounds: [],
    probe: null,
  })
  const [tool, setTool] = useState<Tool>('select')
  const [wireStart, setWireStart] = useState<Point | null>(null)
  const [wirePreview, setWirePreview] = useState<Point | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [live, setLive] = useState<CompileResult>({ errors: [] })
  const svgRef = useRef<SVGSVGElement>(null)
  const idCounter = useRef(0)
  const dragRef = useRef<{ id: string; dx: number; dy: number } | null>(null)
  // 배선 진행 상태는 ref가 진실이다 — 포인터 이벤트가 리렌더보다 빨리
  // 연달아 와도 stale state를 보지 않는다 (state는 미리보기 렌더용)
  const wireStartRef = useRef<Point | null>(null)
  const wireMovedRef = useRef(false)
  const liveCallback = useRef(onLiveNetlist)
  liveCallback.current = onLiveNetlist

  const selected = schematic.parts.find((part) => part.id === selectedId) ?? null

  // 그리는 즉시 netlist로 파싱: 결과(또는 오류)를 항상 최신으로 유지한다
  useEffect(() => {
    const result = compileSchematic(schematic)
    setLive(result)
    liveCallback.current?.(result.netlist ?? null, result.errors)
  }, [schematic])

  const nextName = (kind: PartKind): string => {
    let index = 1
    const taken = new Set(schematic.parts.map((part) => part.name.toUpperCase()))
    while (taken.has(`${kind}${index}`)) index++
    return `${kind}${index}`
  }

  const gridPoint = (event: React.PointerEvent): Point => {
    const rect = svgRef.current!.getBoundingClientRect()
    // viewBox 스케일(반응형 축소) 보정 후 격자로 스냅
    const scale = rect.width / (COLS * GRID + PAD * 2)
    const x = Math.round(((event.clientX - rect.left) / scale - PAD) / GRID)
    const y = Math.round(((event.clientY - rect.top) / scale - PAD) / GRID)
    return { x: Math.max(0, Math.min(COLS, x)), y: Math.max(0, Math.min(ROWS, y)) }
  }

  const removePart = (id: string) => {
    setSchematic((prev) => ({ ...prev, parts: prev.parts.filter((p) => p.id !== id) }))
    if (selectedId === id) setSelectedId(null)
  }

  const updateSelected = (changes: Partial<Part>) => {
    if (!selected) return
    setSchematic((prev) => ({
      ...prev,
      parts: prev.parts.map((part) =>
        part.id === selected.id ? { ...part, ...changes } : part,
      ),
    }))
  }

  // 키보드: R 회전, Delete 삭제 (입력 필드에 타이핑 중일 때는 무시)
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLInputElement) return
      if (!selectedId) return
      if (event.key === 'r' || event.key === 'R') {
        setSchematic((prev) => ({
          ...prev,
          parts: prev.parts.map((part) =>
            part.id === selectedId ? { ...part, vertical: !part.vertical } : part,
          ),
        }))
      } else if (event.key === 'Delete' || event.key === 'Backspace') {
        removePart(selectedId)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId])

  const commitWire = (start: Point, end: Point) => {
    const wires: Wire[] = []
    if (start.x !== end.x) {
      wires.push({ x1: start.x, y1: start.y, x2: end.x, y2: start.y })
    }
    if (start.y !== end.y) {
      wires.push({ x1: end.x, y1: start.y, x2: end.x, y2: end.y })
    }
    if (wires.length > 0) {
      setSchematic((prev) => ({ ...prev, wires: [...prev.wires, ...wires] }))
    }
  }

  const canvasPointerDown = (event: React.PointerEvent) => {
    const point = gridPoint(event)
    capturePointer(svgRef.current, event.pointerId)

    if (tool === 'wire') {
      if (wireStartRef.current) {
        // 클릭-클릭 방식 두 번째 클릭
        commitWire(wireStartRef.current, point)
        wireStartRef.current = null
        setWireStart(null)
        setWirePreview(null)
      } else {
        wireStartRef.current = point
        wireMovedRef.current = false
        setWireStart(point)
        setWirePreview(point)
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
      setTool('select') // 배치 직후 드래그로 위치 조정 가능하게
      return
    }
    if (tool === 'select') {
      setSelectedId(null) // 빈 캔버스 클릭 → 선택 해제
    }
  }

  const canvasPointerMove = (event: React.PointerEvent) => {
    if (dragRef.current) {
      const point = gridPoint(event)
      const { id, dx, dy } = dragRef.current
      setSchematic((prev) => ({
        ...prev,
        parts: prev.parts.map((part) =>
          part.id === id
            ? {
                ...part,
                x: Math.max(0, Math.min(COLS, point.x + dx)),
                y: Math.max(0, Math.min(ROWS, point.y + dy)),
              }
            : part,
        ),
      }))
      return
    }
    const start = wireStartRef.current
    if (tool === 'wire' && start) {
      const point = gridPoint(event)
      if (point.x !== start.x || point.y !== start.y) {
        wireMovedRef.current = true
      }
      setWirePreview(point)
    }
  }

  const canvasPointerUp = (event: React.PointerEvent) => {
    if (dragRef.current) {
      dragRef.current = null
      return
    }
    const start = wireStartRef.current
    if (tool === 'wire' && start && wireMovedRef.current) {
      // 드래그 방식: 누른 채 끌어서 놓으면 즉시 확정
      commitWire(start, gridPoint(event))
      wireStartRef.current = null
      setWireStart(null)
      setWirePreview(null)
    }
  }

  const partPointerDown = (event: React.PointerEvent, part: Part) => {
    // 배선·접지·프로브 등 캔버스 도구는 부품 단자 위에서도 동작해야 하므로
    // 선택/삭제 도구일 때만 부품이 이벤트를 소비한다
    if (tool !== 'select' && tool !== 'delete') return
    event.stopPropagation()
    if (tool === 'delete') {
      removePart(part.id)
      return
    }
    setSelectedId(part.id)
    const point = gridPoint(event)
    dragRef.current = { id: part.id, dx: part.x - point.x, dy: part.y - point.y }
    capturePointer(svgRef.current, event.pointerId)
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

  const exportToTextEditor = () => {
    if (live.netlist) onCompile(live.netlist)
  }

  const junctions = junctionPoints(schematic)

  return (
    <div className="schematic">
      <div className="tool-bar">
        <button className={tool === 'select' ? 'active' : ''} onClick={() => setTool('select')}>
          선택/이동
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
        <button
          className={tool === 'wire' ? 'active' : ''}
          onClick={() => {
            setTool('wire')
            wireStartRef.current = null
            setWireStart(null)
            setWirePreview(null)
          }}
        >
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
        viewBox={`0 0 ${COLS * GRID + PAD * 2} ${ROWS * GRID + PAD * 2}`}
        className="schematic-canvas"
        onPointerDown={canvasPointerDown}
        onPointerMove={canvasPointerMove}
        onPointerUp={canvasPointerUp}
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

        {wireStart && wirePreview && (
          <path
            d={`M${toPx(wireStart.x)},${toPx(wireStart.y)} H${toPx(wirePreview.x)} V${toPx(wirePreview.y)}`}
            stroke="#4b5cc4"
            strokeWidth={2}
            strokeDasharray="5 4"
            fill="none"
            pointerEvents="none"
          />
        )}

        {schematic.parts.map((part) => {
          const [first, second] = terminals(part)
          const midX = (toPx(first.x) + toPx(second.x)) / 2
          const midY = (toPx(first.y) + toPx(second.y)) / 2
          const isSelected = part.id === selectedId
          return (
            <g key={part.id}>
              <g
                transform={`translate(${toPx(part.x)},${toPx(part.y)})${part.vertical ? ' rotate(90)' : ''}`}
                color={isSelected ? '#4b5cc4' : '#2b2b33'}
                onPointerDown={(event) => partPointerDown(event, part)}
                style={{ cursor: tool === 'select' ? 'grab' : 'pointer' }}
              >
                {isSelected && (
                  <rect
                    x={-6}
                    y={-18}
                    width={PART_PX + 12}
                    height={36}
                    rx={6}
                    fill="#eef2ff"
                    stroke="#c7d0f0"
                  />
                )}
                <rect x={-6} y={-16} width={PART_PX + 12} height={32} fill="transparent" />
                <SymbolBody kind={part.kind} />
                <circle cx={0} cy={0} r={3} fill="#4b5cc4" />
                <circle cx={PART_PX} cy={0} r={3} fill="#2b2b33" />
              </g>
              <text
                x={part.vertical ? midX + 20 : midX}
                y={part.vertical ? midY + 4 : midY + 26}
                textAnchor={part.vertical ? 'start' : 'middle'}
                fontSize={11}
                fill="#6b6375"
                pointerEvents="none"
              >
                {part.name}={part.value}
                {part.ic?.trim() ? ` (IC=${part.ic.trim()})` : ''}
              </text>
            </g>
          )
        })}

        {junctions.map((point, index) => (
          <circle
            key={`j${index}`}
            cx={toPx(point.x)}
            cy={toPx(point.y)}
            r={3.5}
            fill="#2b2b33"
            pointerEvents="none"
          />
        ))}

        {schematic.grounds.map((ground, index) => (
          <g key={`g${index}`} onClick={(event) => groundClick(event, index)}>
            <line x1={toPx(ground.x)} y1={toPx(ground.y)} x2={toPx(ground.x)} y2={toPx(ground.y) + 8} stroke="#2b2b33" strokeWidth={2} />
            <line x1={toPx(ground.x) - 8} y1={toPx(ground.y) + 8} x2={toPx(ground.x) + 8} y2={toPx(ground.y) + 8} stroke="#2b2b33" strokeWidth={2} />
            <line x1={toPx(ground.x) - 5} y1={toPx(ground.y) + 12} x2={toPx(ground.x) + 5} y2={toPx(ground.y) + 12} stroke="#2b2b33" strokeWidth={2} />
            <line x1={toPx(ground.x) - 2} y1={toPx(ground.y) + 16} x2={toPx(ground.x) + 2} y2={toPx(ground.y) + 16} stroke="#2b2b33" strokeWidth={2} />
          </g>
        ))}

        {schematic.probe && (
          <g pointerEvents="none">
            <circle cx={toPx(schematic.probe.x)} cy={toPx(schematic.probe.y)} r={8} fill="none" stroke="#c2410c" strokeWidth={2} />
            <text x={toPx(schematic.probe.x)} y={toPx(schematic.probe.y) - 12} textAnchor="middle" fontSize={11} fill="#c2410c">
              V(out)
            </text>
          </g>
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
          <button onClick={() => updateSelected({ vertical: !selected.vertical })}>회전 (R)</button>
          <button onClick={() => removePart(selected.id)}>삭제 (Del)</button>
        </div>
      )}

      {live.errors.length > 0 ? (
        <div className="error-box">
          {live.errors.map((error, index) => (
            <div key={index}>• {error}</div>
          ))}
        </div>
      ) : (
        live.netlist && (
          <div className="schematic-preview">
            <div className="preview-head">
              <span>✓ 실시간 파싱 완료 — 이대로 "해석 실행" 가능</span>
              <button className="ghost-button" onClick={exportToTextEditor}>
                텍스트 에디터로 보내기
              </button>
            </div>
            <pre>{live.netlist}</pre>
          </div>
        )
      )}
      <p className="muted">
        부품 도구로 캔버스를 클릭해 배치(자동으로 선택/이동 모드 전환), 드래그로 이동,
        R 키로 회전, Del 키로 삭제. 배선은 누른 채 드래그(또는 두 점 클릭).
        접지와 출력 프로브는 필수입니다.
      </p>
    </div>
  )
}
