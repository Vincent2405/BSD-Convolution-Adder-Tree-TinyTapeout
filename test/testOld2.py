# SPDX-FileCopyrightText: © 2024 Tiny Tapeout
# SPDX-License-Identifier: Apache-2.0
#
# Test: echte Pixelwerte (0..255) in 9 Register w0..w8 schreiben, die HW rechnet
# intern Bitebenen -> Preadd-ROM -> Adder-Tree -> BSD. Jetzt 9 UNABHAENGIGE Pixel
# (en + sel8 sind gefixt).
#
# Pin-Belegung uio_in[7:0] = [WRITE, EN, outSel1, outSel0, regSel3..0]
#   uio_in[7]    = WRITE   (1 = schreiben)
#   uio_in[6]    = EN      (1 = Bitebenen-Counter laeuft / rechnen)
#   uio_in[5:4]  = outSel  (welcher der 4 Lese-Chunks)
#   uio_in[3:0]  = regSel  (Register 0..8)
#
#   Schreiben:  ui_in=Pixel, uio_in = 0x80 | regSel          (WRITE=1, EN=0)
#   Rechnen:    uio_in = 0b0100_0000 (=0x40) DAUERHAFT        (EN=1)
#   Lesen:      uio_in = chunk << 4                           (WRITE=0, EN=0)

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles


FILTER = [1, 2, 1, 2, 4, 2, 1, 2, 1]   # palindromisch -> regSel i hat Gewicht FILTER[i]
NUM_PIXELS = 9
ENABLE = 1 << 6                         # uio_in: EN=1 (Bit6)
ENABLE_CYCLES = 9                       # Bitebenen-Counter laeuft 0..7 -> 8 Schritte (+1 Reserve)


def decode_bsd_digit(two_bits: int) -> int:
    return {0b00: -1, 0b01: 0, 0b10: 0, 0b11: 1}[two_bits]


def decode_bsd_value(raw: int, digits: int) -> int:
    return sum(decode_bsd_digit((raw >> (2 * i)) & 0b11) * (1 << i)
               for i in range(digits))


def make_write_select(register_index: int) -> int:
    """WRITE=Bit7, regSel=Bit3..0 (EN=0, outSel=0)."""
    assert 0 <= register_index <= 8
    return (1 << 7) | (register_index & 0b1111)


def make_read_select(chunk_index: int) -> int:
    """outSel=Bit5..4 (WRITE=0, EN=0)."""
    assert 0 <= chunk_index <= 3
    return (chunk_index & 0b11) << 4


def gaussian_expected(pixels: list[int]) -> int:
    assert len(pixels) == NUM_PIXELS
    for p in pixels:
        assert 0 <= p <= 255
    return sum(p * w for p, w in zip(pixels, FILTER))


def random_pixels(rng: random.Random) -> list[int]:
    return [rng.randint(0, 255) for _ in range(NUM_PIXELS)]


async def reset_dut(dut):
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 10)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 1)


async def run_one_matrix(dut, pixels: list[int], BSD_DIGITS: int = 14):
    expected = gaussian_expected(pixels)

    # 9 Pixel in Register w0..w8 schreiben (regSel 0..8, WRITE=1, EN=0)
    for reg in range(NUM_PIXELS):
        dut.ui_in.value = pixels[reg] & 0xFF
        dut.uio_in.value = make_write_select(reg)
        await ClockCycles(dut.clk, 1)

    # Rechnen: EN=1 dauerhaft, Bitebenen-Counter laeuft 0..7, fuellt o1..o8
    dut.ui_in.value = 0
    dut.uio_in.value = ENABLE
    await ClockCycles(dut.clk, ENABLE_CYCLES)

    # BSD-Ergebnis in vier 8-bit-Chunks lesen (EN=0, WRITE=0 -> eingefroren)
    raw_bsd = 0
    chunks = []
    for chunk in range(4):
        dut.uio_in.value = make_read_select(chunk)
        await ClockCycles(dut.clk, 1)
        chunk_value = int(dut.uo_out.value) & 0xFF
        chunks.append(chunk_value)
        raw_bsd |= chunk_value << (8 * chunk)

    actual = decode_bsd_value(raw_bsd, BSD_DIGITS)
    return actual, expected, raw_bsd, chunks


@cocotb.test()
async def test_gaussian_pixel_matrices(dut):
    NUM_MATRICES = 100
    SEED = 1234
    rng = random.Random(SEED)

    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    await reset_dut(dut)

    dut._log.info(
        f"Teste {NUM_MATRICES} zufaellige Pixel-Matrizen (seed={SEED}), "
        f"FILTER={FILTER}"
    )

    for i in range(NUM_MATRICES):
        pixels = random_pixels(rng)

        actual, expected, raw_bsd, chunks = await run_one_matrix(dut, pixels)

        dut._log.info(
            f"[{i + 1:3d}/{NUM_MATRICES}] pixels={pixels} "
            f"expected={expected} actual={actual}"
        )

        assert actual == expected, (
            f"Matrix {i + 1}/{NUM_MATRICES} falsch: "
            f"expected={expected}, got={actual}. "
            f"pixels={pixels}, raw_bsd=0x{raw_bsd:08x}, "
            f"raw_bsd=0b{raw_bsd:032b}, chunks={[hex(c) for c in chunks]}"
        )

        # Vor der naechsten Matrix zuruecksetzen -> definierte Startwerte
        # (setzt voraus, dass rst den Bitebenen-Counter UND das Done-Flag s108
        #  zuruecksetzt -- siehe 'Bug 2'. Falls Matrix 2+ stale Werte liefert,
        #  ist das noch offen -> dann NUM_MATRICES=1 setzen.)
        await reset_dut(dut)

    dut._log.info(f"Alle {NUM_MATRICES} Matrizen korrekt.")
