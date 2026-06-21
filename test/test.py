# SPDX-FileCopyrightText: © 2024 Tiny Tapeout
# SPDX-License-Identifier: Apache-2.0
#
# Tests fuer TinyTapeoutAdderTreeMitSPI_HDC (kombiniert: Faltung + SPI-Reader + HDC).
#
# NEUE Pin-Belegung uio_in[7:0] (uio7 = MODE):
#   uio_in[7] = MODE      (0 = Faltung, 1 = SPI+HDC)
#   uio_in[6] = outSel[1]  (in SPI-Mode ungenutzt)
#   uio_in[5] = outSel[0]  (in SPI-Mode ungenutzt)
#   uio_in[4] = write     | START   (je nach MODE)
#   uio_in[1] = en        | MISO     (je nach MODE)
#   uio_in[0/2/3]         = MOSI/SCK/CS -> AUSGAENGE (uio_oe=0x0D), hier nicht getrieben
#
# Faltung (MODE=0): Register-Schreibzeiger AUTO-INKREMENTIERT (kein regSel mehr).
#   Schreiben:  ui_in=Pixel, uio_in=0x10 (write=1)  -> 9x in Folge fuellt R0..R8
#   Rechnen:    uio_in=0x02 (en=1) fuer 9 Takte
#   Lesen:      uio_in=outSel<<5 (write=0, en=0)     -> 4 Chunks auf uo_out
#
# SPI+HDC (MODE=1): SPI liest 4x8bit (R0..R3) aus dem RAM, HDC rechnet
#   BUNDLE = (R0 ^ R2) & (R3 ^ R1)  -> auf uo_out.

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles


FILTER = [1, 2, 1, 2, 4, 2, 1, 2, 1]   # palindromisch -> Register i hat Gewicht FILTER[i]
NUM_PIXELS = 9
ENABLE_CYCLES = 9                       # Bitebenen-Counter 0..7 -> 8 Schritte (+1 Reserve)

# Bit-Positionen in uio_in
MODE_BIT, OUTSEL1, OUTSEL0, WRITE_BIT, EN_BIT = 7, 6, 5, 4, 1
START_BIT, MISO_BIT = 4, 1              # im SPI-Mode teilen sich write/START bzw. en/MISO die Pins
MODE = 1 << MODE_BIT


# ---------------------------------------------------------------- Clock
_clk_task = None


def ensure_clock(dut):
    """Genau EINE Clock ueber alle Tests. Mehrere @cocotb.test() duerfen NICHT je
    eine eigene Clock auf dut.clk starten -- konkurrierende Treiber verstuemmeln
    den Takt (Test 2 sah sonst nur 0x00). Alte Clock killen, frische starten."""
    global _clk_task
    if _clk_task is not None:
        try:
            _clk_task.kill()
        except Exception:
            pass
    _clk_task = cocotb.start_soon(Clock(dut.clk, 10, unit="us").start())


# ---------------------------------------------------------------- BSD-Decode
def decode_bsd_digit(two_bits: int) -> int:
    return {0b00: -1, 0b01: 0, 0b10: 0, 0b11: 1}[two_bits]


def decode_bsd_value(raw: int, digits: int) -> int:
    return sum(decode_bsd_digit((raw >> (2 * i)) & 0b11) * (1 << i)
               for i in range(digits))


# ---------------------------------------------------------------- Faltung (MODE=0)
def m0_write() -> int:
    """write=1, en=0, MODE=0 -> Pixel ins naechste Register (Auto-Increment)."""
    return 1 << WRITE_BIT


def m0_run() -> int:
    """en=1, write=0, MODE=0 -> Bitebenen-Counter laeuft."""
    return 1 << EN_BIT


def m0_read(chunk: int) -> int:
    """outSel=Bit6:5, write=0, en=0, MODE=0."""
    assert 0 <= chunk <= 3
    return ((chunk & 1) << OUTSEL0) | (((chunk >> 1) & 1) << OUTSEL1)


def gaussian_expected(pixels: list[int]) -> int:
    assert len(pixels) == NUM_PIXELS
    for p in pixels:
        assert 0 <= p <= 255
    return sum(p * w for p, w in zip(pixels, FILTER))


def random_pixels(rng: random.Random) -> list[int]:
    return [rng.randint(0, 255) for _ in range(NUM_PIXELS)]


# ---------------------------------------------------------------- SPI+HDC (MODE=1)
def hdc_expected(r: list[int]) -> int:
    """HDC_Calc-Verdrahtung: BUNDLE = (R0 ^ R2) & (R3 ^ R1)."""
    assert len(r) == 4
    return (r[0] ^ r[2]) & (r[3] ^ r[1])


# ---------------------------------------------------------------- Helpers
async def reset_dut(dut):
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0          # MODE=0, alle Steuersignale 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 10)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 1)


async def run_one_matrix(dut, pixels: list[int], BSD_DIGITS: int = 14):
    expected = gaussian_expected(pixels)

    # 9 Pixel in Folge schreiben -> Auto-Increment fuellt R0..R8 (kein regSel)
    for reg in range(NUM_PIXELS):
        dut.ui_in.value = pixels[reg] & 0xFF
        dut.uio_in.value = m0_write()
        await ClockCycles(dut.clk, 1)

    # Rechnen: en=1 dauerhaft, Bitebenen-Counter 0..7
    dut.ui_in.value = 0
    dut.uio_in.value = m0_run()
    await ClockCycles(dut.clk, ENABLE_CYCLES)

    # BSD-Ergebnis in vier 8-bit-Chunks lesen (eingefroren)
    raw_bsd = 0
    chunks = []
    for chunk in range(4):
        dut.uio_in.value = m0_read(chunk)
        await ClockCycles(dut.clk, 1)
        chunk_value = int(dut.uo_out.value) & 0xFF
        chunks.append(chunk_value)
        raw_bsd |= chunk_value << (8 * chunk)

    actual = decode_bsd_value(raw_bsd, BSD_DIGITS)
    return actual, expected, raw_bsd, chunks


async def spi_read_hdc(dut, r_bytes: list[int]) -> int:
    """Treibt den SPI-Reader (MODE=1) mit dem MISO-Strom fuer R0..R3, gibt uo_out (=HDC_Out)."""
    assert len(r_bytes) == 4
    # START-Puls (uio4), genau 1 Takt
    dut.uio_in.value = MODE | (1 << START_BIT)
    await ClockCycles(dut.clk, 1)
    dut.uio_in.value = MODE                       # START low, MISO=0
    # 24 SCK cmd+addr (MISO egal), je 2 CLK-Flanken (interner CLK = 2x SCK)
    for _ in range(24):
        dut.uio_in.value = MODE
        await ClockCycles(dut.clk, 2)
    # 32 Datenbits: R0..R3, je 8 bit MSB-first
    bits = [(b >> pos) & 1 for b in r_bytes for pos in range(7, -1, -1)]
    for bit in bits:
        dut.uio_in.value = MODE | (bit << MISO_BIT)
        await ClockCycles(dut.clk, 2)
    dut.uio_in.value = MODE
    await ClockCycles(dut.clk, 1)
    return int(dut.uo_out.value) & 0xFF
# ---------------------------------------------------------------- Tests
@cocotb.test()
async def test_gaussian_pixel_matrices(dut):
    """MODE=0: 100 zufaellige 3x3-Patches durch die Faltung."""
    NUM_MATRICES = 100
    SEED = 1234
    rng = random.Random(SEED)

    ensure_clock(dut)
    await reset_dut(dut)

    dut._log.info(f"Faltung: {NUM_MATRICES} Matrizen (seed={SEED}), FILTER={FILTER}")

    for i in range(NUM_MATRICES):
        pixels = random_pixels(rng)
        actual, expected, raw_bsd, chunks = await run_one_matrix(dut, pixels)
        dut._log.info(f"[{i + 1:3d}/{NUM_MATRICES}] pixels={pixels} "
                      f"expected={expected} actual={actual}")
        assert actual == expected, (
            f"Matrix {i + 1}/{NUM_MATRICES} falsch: expected={expected}, got={actual}. "
            f"pixels={pixels}, raw_bsd=0b{raw_bsd:032b}, chunks={[hex(c) for c in chunks]}")
        await reset_dut(dut)        # rst setzt Bitebenen-Counter UND Done-Flag zurueck

    dut._log.info(f"Alle {NUM_MATRICES} Matrizen korrekt.")
#
