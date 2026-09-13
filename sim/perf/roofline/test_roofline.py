#!/usr/bin/env python3
# Pure-function unit tests for roofline.py; no Verilator or numpy-heavy fixtures needed.
import csv
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import roofline as rl


class TestMemoryBytes(unittest.TestCase):
    def test_4x4_m8_hand_computed(self):
        # N=4, M=8: W = 4 words * 4 int8 = 16B, A = 8 words * 4 int8 = 32B,
        # C = 8 words * 4 int32 = 128B, ideal_macs = 8*4*4 = 128.
        w, a, c = rl.memory_bytes(N=4, M=8)
        self.assertEqual(w, 16)
        self.assertEqual(a, 32)
        self.assertEqual(c, 128)


class TestComputeEnergy(unittest.TestCase):
    def test_hand_computed_4x4_m8(self):
        row = {"N": 4, "M": 8, "ideal_macs": 128}
        tech = {
            "energy_mac_int8_pJ": 1.0,
            "energy_sram_byte_read_pJ": 1.0,
            "energy_sram_byte_write_pJ": 2.0,
        }
        e = rl.compute_energy(row, tech)
        # e_compute = 128 * 1.0 = 128
        # e_mem_rd = (16 + 32) * 1.0 = 48
        # e_mem_wr = 128 * 2.0 = 256
        # e_total = 432
        self.assertAlmostEqual(e["e_compute_pJ"], 128.0)
        self.assertAlmostEqual(e["e_mem_rd_pJ"], 48.0)
        self.assertAlmostEqual(e["e_mem_wr_pJ"], 256.0)
        self.assertAlmostEqual(e["e_total_pJ"], 432.0)
        self.assertAlmostEqual(e["pj_per_mac"], 1.0)
        self.assertAlmostEqual(e["eff_pj_per_mac"], 432.0 / 128.0)

    def test_eff_pj_per_mac_ge_intrinsic(self):
        # Data movement can only add energy on top of the intrinsic MAC cost.
        row = {"N": 8, "M": 32, "ideal_macs": 8 * 8 * 32}
        tech = {"energy_mac_int8_pJ": 0.2, "energy_sram_byte_read_pJ": 1.0, "energy_sram_byte_write_pJ": 1.0}
        e = rl.compute_energy(row, tech)
        self.assertGreaterEqual(e["eff_pj_per_mac"], e["pj_per_mac"])


class TestArithmeticIntensity(unittest.TestCase):
    def test_4x4_m8(self):
        row = {"N": 4, "M": 8, "ideal_macs": 128}
        # read_bytes = 16 + 32 = 48; AI = 128/48
        self.assertAlmostEqual(rl.arithmetic_intensity(row), 128.0 / 48.0)


class TestRidgePoint(unittest.TestCase):
    def test_n8(self):
        peak, bpc, ridge_ai = rl.ridge_point(8)
        self.assertEqual(peak, 64)
        self.assertEqual(bpc, 8)
        self.assertAlmostEqual(ridge_ai, 8.0)

    def test_n16(self):
        peak, bpc, ridge_ai = rl.ridge_point(16)
        self.assertEqual(peak, 256)
        self.assertEqual(bpc, 16)
        self.assertAlmostEqual(ridge_ai, 16.0)

    def test_ridge_is_where_roofs_cross(self):
        # By construction memory roof (AI*bpc) must equal compute roof (peak) at ridge_ai.
        for N in (4, 8, 16):
            peak, bpc, ridge_ai = rl.ridge_point(N)
            self.assertAlmostEqual(ridge_ai * bpc, peak)


class TestTopsPerWatt(unittest.TestCase):
    def test_positive_and_finite(self):
        row = {"N": 4, "M": 16, "ideal_macs": 256, "cycles": 22, "macs_per_cycle": 11.636}
        tech = {
            "energy_mac_int8_pJ": 0.23, "energy_sram_byte_read_pJ": 1.25,
            "energy_sram_byte_write_pJ": 1.25,
        }
        e = rl.compute_energy(row, tech)
        tpw = rl.tops_per_watt(row, e, freq_mhz=500)
        self.assertGreater(tpw, 0.0)
        self.assertTrue(tpw == tpw)  # not NaN


class TestParseResultsCsv(unittest.TestCase):
    def test_parses_types(self):
        content = (
            "N,M,scenario,cycles,ideal_macs,macs_per_cycle,utilization_pct,tops_at_freq\n"
            "4,4,single_load,10,64,6.400000,40.0000,0.006400\n"
        )
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_test_tmp.csv")
        with open(path, "w") as f:
            f.write(content)
        try:
            rows = rl.parse_results_csv(path)
            self.assertEqual(len(rows), 1)
            r = rows[0]
            self.assertEqual(r["N"], 4)
            self.assertEqual(r["M"], 4)
            self.assertEqual(r["scenario"], "single_load")
            self.assertEqual(r["cycles"], 10)
            self.assertEqual(r["ideal_macs"], 64)
            self.assertAlmostEqual(r["macs_per_cycle"], 6.4)
            self.assertAlmostEqual(r["utilization_pct"], 40.0)
            self.assertAlmostEqual(r["tops_at_freq"], 0.0064)
        finally:
            os.remove(path)


class TestTechParams(unittest.TestCase):
    def test_loads_and_has_required_fields(self):
        tech_params = rl.load_tech_params()
        self.assertIn("target_freq_mhz", tech_params)
        for name, node in tech_params["nodes"].items():
            for key in ("energy_mac_int8_pJ", "energy_reg_bitflip_pJ",
                        "energy_sram_byte_read_pJ", "energy_sram_byte_write_pJ", "source"):
                self.assertIn(key, node, f"{name} missing {key}")


if __name__ == "__main__":
    unittest.main()
