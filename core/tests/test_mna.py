"""MNA stamp and assembly tests (design §4.3, ADR-7)."""

import sympy as sp

from circuitsolver import parse
from circuitsolver.mna import assemble, s

R1, R2 = sp.symbols("R1 R2", positive=True)
L, C = sp.symbols("L C", positive=True)
Vi = sp.Symbol("Vi")


class TestAssembly:
    def test_voltage_divider_system(self):
        system = assemble(parse("Vin in 0 Vi\nR1 in out R1\nR2 out 0 R2\n"))
        assert system.nodes == ("in", "out")
        assert [str(u) for u in system.unknowns] == ["v_in", "v_out", "i_Vin"]
        assert system.A == sp.Matrix(
            [
                [1 / R1, -1 / R1, 1],
                [-1 / R1, 1 / R1 + 1 / R2, 0],
                [1, 0, 0],
            ]
        )
        assert system.z == sp.Matrix([[0], [0], [Vi]])

    def test_reactive_admittances(self):
        system = assemble(parse("V1 a 0 Vi\nL1 a b L\nC1 b 0 C\n"))
        i_a, i_b = system.node_index["a"], system.node_index["b"]
        assert system.A[i_a, i_a] == 1 / (s * L)
        assert system.A[i_a, i_b] == -1 / (s * L)
        assert system.A[i_b, i_b] == 1 / (s * L) + s * C

    def test_current_source_rhs(self):
        system = assemble(parse("I1 0 a 2\nR1 a 0 1k\n"))
        assert system.A == sp.Matrix([[sp.Rational(1, 1000)]])
        assert system.z == sp.Matrix([[2]])

    def test_ground_contributions_dropped(self):
        system = assemble(parse("R1 a 0 1k\nV1 a 0 1\n"))
        i_a = system.node_index["a"]
        assert system.A[i_a, i_a] == sp.Rational(1, 1000)

    def test_parallel_elements_accumulate(self):
        system = assemble(parse("R1 a 0 R1\nR2 a 0 R2\nV1 a 0 1\n"))
        i_a = system.node_index["a"]
        assert system.A[i_a, i_a] == 1 / R1 + 1 / R2


class TestStampRecords:
    def test_records_follow_netlist_order(self):
        system = assemble(parse("Vin in 0 Vi\nR1 in out R1\nR2 out 0 R2\n"))
        assert [record.component for record in system.records] == ["Vin", "R1", "R2"]

    def test_admittance_stamp_has_four_entries(self):
        system = assemble(parse("Vin in 0 Vi\nR1 in out R1\nR2 out 0 R2\n"))
        r1 = system.records[1]
        positions = {(entry.row, entry.col) for entry in r1.entries}
        assert positions == {(0, 0), (1, 1), (0, 1), (1, 0)}
        assert all(entry.target == "A" for entry in r1.entries)

    def test_grounded_stamp_entries_are_dropped(self):
        system = assemble(parse("Vin in 0 Vi\nR1 in out R1\nR2 out 0 R2\n"))
        # R2 (out-0): only the diagonal contribution survives
        r2 = system.records[2]
        assert [(entry.row, entry.col) for entry in r2.entries] == [(1, 1)]

    def test_voltage_source_stamps_matrix_and_rhs(self):
        system = assemble(parse("Vin in 0 Vi\nR1 in out R1\nR2 out 0 R2\n"))
        vin = system.records[0]
        a_entries = {(e.row, e.col) for e in vin.entries if e.target == "A"}
        k = system.current_index["Vin"]
        assert a_entries == {(0, k), (k, 0)}
        z_entries = [e for e in vin.entries if e.target == "z"]
        assert len(z_entries) == 1
        assert z_entries[0].row == k
        assert z_entries[0].col is None
        assert z_entries[0].term == Vi
