"""단계별 회로 단순화 (design §4.9, Phase 5).

원칙: H(s) 계산은 항상 MNA로 하고, 단순화는 **설명용 병렬 트랙**이다.
브리지처럼 끝까지 단순화되지 않는 회로가 많으므로 결과 산출을 여기에
의존시키지 않는다.

세 규칙을 고정점까지 반복 적용하고 각 적용을 기록한다:
  * 병렬 결합 — 같은 종류 수동 소자가 같은 노드쌍에 걸린 경우
  * 직렬 결합 — 차수 2 내부 노드로만 이어진 같은 종류 수동 소자
  * 전원 변환 — 전압원 + 직렬 저항 → Norton 등가 (한 방향만:
    양방향 Thévenin↔Norton은 고정점이 없다)

보존 대상: 접지, .out 출력 노드, .out 입력 전원, 초기조건이 붙은 소자.
출력이 지정된 회로에서 단계가 적용되면 원본과 단순화본의 H(s)가 같은지
MNA로 자체 검증한다.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

import sympy as sp

from .circuit import Circuit, Component, ComponentType
from .errors import CircuitError
from .graph import GROUND

_PASSIVE = (ComponentType.RESISTOR, ComponentType.INDUCTOR, ComponentType.CAPACITOR)
_MAX_ITERATIONS = 100


@dataclass(frozen=True)
class SimplificationStep:
    rule: str  # "parallel" | "series" | "source_transform"
    description: str
    latex: str
    removed: tuple[str, ...]
    created: tuple[str, ...]


@dataclass(frozen=True)
class SimplificationResult:
    steps: tuple[SimplificationStep, ...]
    circuit: Circuit
    verified: bool | None  # H(s) 보존 확인 결과 (출력 미지정/검증 불가 시 None)


def _mergeable(comp: Component, protected: set[str]) -> bool:
    return (
        comp.ctype in _PASSIVE
        and comp.ic is None
        and comp.name.upper() not in protected
    )


def _combine_series(ctype: ComponentType, v1: sp.Expr, v2: sp.Expr) -> sp.Expr:
    if ctype is ComponentType.CAPACITOR:
        return sp.cancel(v1 * v2 / (v1 + v2))
    return v1 + v2  # R, L


def _combine_parallel(ctype: ComponentType, v1: sp.Expr, v2: sp.Expr) -> sp.Expr:
    if ctype is ComponentType.CAPACITOR:
        return v1 + v2
    return sp.cancel(v1 * v2 / (v1 + v2))  # R, L


def _node_degree(components: list[Component], node: str) -> int:
    return sum(comp.nodes.count(node) for comp in components)


def _try_parallel(components, protected_comps, counter):
    for a, b in itertools.combinations(components, 2):
        if not (_mergeable(a, protected_comps) and _mergeable(b, protected_comps)):
            continue
        if a.ctype is not b.ctype or set(a.nodes) != set(b.nodes):
            continue
        letter = a.ctype.value
        value = _combine_parallel(a.ctype, a.value, b.value)
        name = f"{letter}eq{next(counter)}"
        merged = Component(name=name, ctype=a.ctype, nodes=a.nodes, value=value)
        formula = (
            f"{sp.latex(a.value)} + {sp.latex(b.value)}"
            if a.ctype is ComponentType.CAPACITOR
            else rf"\frac{{{sp.latex(a.value)} \cdot {sp.latex(b.value)}}}{{{sp.latex(a.value)} + {sp.latex(b.value)}}}"
        )
        step = SimplificationStep(
            rule="parallel",
            description=f"{a.name} ∥ {b.name} 병렬 결합 → {name}",
            latex=rf"{letter}_{{eq}} = {formula} = {sp.latex(value)}",
            removed=(a.name, b.name),
            created=(name,),
        )
        return [c for c in components if c not in (a, b)] + [merged], step
    return None


def _try_series(components, protected_nodes, protected_comps, counter):
    for a, b in itertools.combinations(components, 2):
        if not (_mergeable(a, protected_comps) and _mergeable(b, protected_comps)):
            continue
        if a.ctype is not b.ctype:
            continue
        shared = set(a.nodes) & set(b.nodes)
        if len(shared) != 1:
            continue
        inner = shared.pop()
        if inner in protected_nodes or _node_degree(components, inner) != 2:
            continue
        outer_a = a.nodes[0] if a.nodes[1] == inner else a.nodes[1]
        outer_b = b.nodes[0] if b.nodes[1] == inner else b.nodes[1]
        letter = a.ctype.value
        value = _combine_series(a.ctype, a.value, b.value)
        name = f"{letter}eq{next(counter)}"
        merged = Component(
            name=name, ctype=a.ctype, nodes=(outer_a, outer_b), value=value
        )
        formula = (
            rf"\frac{{{sp.latex(a.value)} \cdot {sp.latex(b.value)}}}{{{sp.latex(a.value)} + {sp.latex(b.value)}}}"
            if a.ctype is ComponentType.CAPACITOR
            else f"{sp.latex(a.value)} + {sp.latex(b.value)}"
        )
        step = SimplificationStep(
            rule="series",
            description=f"{a.name}–{b.name} 직렬 결합 (내부 노드 {inner} 제거) → {name}",
            latex=rf"{letter}_{{eq}} = {formula} = {sp.latex(value)}",
            removed=(a.name, b.name),
            created=(name,),
        )
        return [c for c in components if c not in (a, b)] + [merged], step
    return None


def _try_source_transform(components, protected_nodes, protected_comps, counter):
    """전압원 + 직렬 저항 → Norton 등가 (V → I 방향만)."""
    for source in components:
        if source.ctype is not ComponentType.VOLTAGE_SOURCE:
            continue
        if source.name.upper() in protected_comps:
            continue
        for inner in source.nodes:
            if inner in protected_nodes or _node_degree(components, inner) != 2:
                continue
            partner = next(
                (
                    c
                    for c in components
                    if c is not source and inner in c.nodes
                ),
                None,
            )
            if (
                partner is None
                or partner.ctype is not ComponentType.RESISTOR
                or not _mergeable(partner, protected_comps)
            ):
                continue
            outer_v = source.nodes[0] if source.nodes[1] == inner else source.nodes[1]
            outer_r = partner.nodes[0] if partner.nodes[1] == inner else partner.nodes[1]
            current = sp.cancel(source.value / partner.value)
            index = next(counter)
            # n+ → n- 방향이 전원 내부 전류: V의 n-가 내부 노드면 o_v로 주입
            if source.nodes[1] == inner:
                nodes = (outer_r, outer_v)
            else:
                nodes = (outer_v, outer_r)
            i_eq = Component(
                name=f"Ieq{index}",
                ctype=ComponentType.CURRENT_SOURCE,
                nodes=nodes,
                value=current,
            )
            r_eq = Component(
                name=f"Req{index}",
                ctype=ComponentType.RESISTOR,
                nodes=(outer_v, outer_r),
                value=partner.value,
            )
            step = SimplificationStep(
                rule="source_transform",
                description=(
                    f"{source.name} + {partner.name} 직렬 → Norton 등가 "
                    f"(Ieq{index} ∥ Req{index}), 내부 노드 {inner} 제거"
                ),
                latex=rf"I_{{eq}} = \frac{{{sp.latex(source.value)}}}{{{sp.latex(partner.value)}}} = {sp.latex(current)}",
                removed=(source.name, partner.name),
                created=(i_eq.name, r_eq.name),
            )
            remaining = [c for c in components if c not in (source, partner)]
            return remaining + [i_eq, r_eq], step
    return None


def simplify_circuit(circuit: Circuit) -> SimplificationResult:
    protected_nodes = {GROUND}
    protected_comps: set[str] = set()
    if circuit.output is not None:
        protected_nodes.add(circuit.output.node)
        protected_comps.add(circuit.output.source.upper())

    components = list(circuit.components)
    steps: list[SimplificationStep] = []
    counter = itertools.count(1)

    for _ in range(_MAX_ITERATIONS):
        outcome = (
            _try_parallel(components, protected_comps, counter)
            or _try_series(components, protected_nodes, protected_comps, counter)
            or _try_source_transform(
                components, protected_nodes, protected_comps, counter
            )
        )
        if outcome is None:
            break
        components, step = outcome
        steps.append(step)

    simplified = Circuit(components=tuple(components), output=circuit.output)

    verified: bool | None = None
    if steps and circuit.output is not None:
        try:
            from .analysis import transfer_function

            original = transfer_function(circuit)
            reduced = transfer_function(simplified)
            verified = bool(sp.simplify(original.expr - reduced.expr) == 0)
        except CircuitError:
            verified = None

    return SimplificationResult(
        steps=tuple(steps), circuit=simplified, verified=verified
    )
