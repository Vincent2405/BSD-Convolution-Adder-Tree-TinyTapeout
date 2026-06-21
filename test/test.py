# SPDX-FileCopyrightText: © 2024 Tiny Tapeout
# SPDX-License-Identifier: Apache-2.0
#
# Tests fuer TinyTapeoutAdderTreeMitSPI_HDC (Faltung + SPI-Reader + HDC).
#
# uio_in[7:0]  (uio7 = MODE: 0 = Faltung, 1 = SPI+HDC):
#   [7]=MODE   [6:5]=outSel   [4]=write|START   [1]=en|MISO
#   [0/2/3]=MOSI/SCK/CS -> Ausgaenge (uio_oe=0x0D)
#
# Faltung (MODE=0): write-Puls schreibt Pixel ins naechste Register (Auto-Increment),
#   en=1 fuer 9 Takte rechnet, outSel liest die 4 BSD-Chunks auf uo_out.
# SPI+HDC (MODE=1): SPI liest R0..R3, HDC = (R0^R1) & (R3^R2) auf uo_out.

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge


FILTER = [1, 2, 1, 2, 4, 2, 1, 2, 1]   # palindromisch -> Register i hat Gewicht FILTER[i]
NUM_PIXELS = 9
ENABLE_CYCLES = 9

# uio_in-Bits
MODE_BIT, OUTSEL1, OUTSEL0, WRITE_BIT, EN_BIT = 7, 6, 5, 4, 1
START_BIT, MISO_BIT = 4, 1             # SPI-Mode teilt sich write|START bzw. en|MISO
MODE = 1 << MODE_BIT


def start_clock(dut):
    """Pro Test ein frischer 10us-Takt (cocotb beendet Tasks zwischen Tests)."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="us").start())


def out_bit(sig, idx):
    """Bit idx (0=LSB) eines Busses als '0'/'1'/'x' -- X-tolerant."""
    v = sig.value
    try:
        return "1" if ((v.to_unsigned() >> idx) & 1) else "0"
    except Exception:
        return str(v[idx]).lower()


async def reset_dut(dut):
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 10)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 1)


# ---------------------------------------------------------------- Faltung (MODE=0)
def decode_bsd(raw, digits=14):
    sd = {0b00: -1, 0b01: 0, 0b10: 0, 0b11: 1}
    return sum(sd[(raw >> (2 * i)) & 0b11] << i for i in range(digits))


async def run_one_matrix(dut, pixels):
    # 9 Pixel der Reihe nach schreiben -> Auto-Increment fuellt R0..R8
    for px in pixels:
        dut.ui_in.value = px & 0xFF
        dut.uio_in.value = 1 << WRITE_BIT
        await ClockCycles(dut.clk, 1)
    # rechnen: en=1, Bitebenen-Counter 0..7
    dut.ui_in.value = 0
    dut.uio_in.value = 1 << EN_BIT
    await ClockCycles(dut.clk, ENABLE_CYCLES)
    # BSD-Ergebnis in 4 Chunks lesen
    raw = 0
    for chunk in range(4):
        dut.uio_in.value = ((chunk & 1) << OUTSEL0) | (((chunk >> 1) & 1) << OUTSEL1)
        await ClockCycles(dut.clk, 1)
        raw |= (int(dut.uo_out.value) & 0xFF) << (8 * chunk)
    return decode_bsd(raw)


# ---------------------------------------------------------------- SPI+HDC (MODE=1)
def hdc_expected(r):
    return (r[0] ^ r[1]) & (r[3] ^ r[2])   # HDC_Calc-Verdrahtung


async def spi_read_hdc(dut, r_bytes):
    """START-Puls, dann 56 SCK MISO einspeisen (interner CLK = 2x SCK), uo_out lesen."""
    dut.uio_in.value = MODE
    await ClockCycles(dut.clk, 2)
    dut.uio_in.value = MODE | (1 << START_BIT)          # START (1 Takt)
    await ClockCycles(dut.clk, 1)
    dut.uio_in.value = MODE
    miso = [0] * 24 + [(b >> p) & 1 for b in r_bytes for p in range(7, -1, -1)]
    for bit in miso:                                    # je 2 Takte = 1 SCK
        dut.uio_in.value = MODE | (bit << MISO_BIT)
        await ClockCycles(dut.clk, 2)
    dut.uio_in.value = MODE
    await ClockCycles(dut.clk, 20)                      # Reserve bis DONE sicher anliegt
    return int(dut.uo_out.value) & 0xFF


# ---------------------------------------------------------------- Tests
@cocotb.test()
async def test_spi_basic_outputs(dut):
    """CS ist idle high; nach START schwingt SCK und MOSI sendet (0x03)."""
    start_clock(dut)
    await reset_dut(dut)
    cs = out_bit(dut.uio_out, 3)
    assert cs == "1", f"CS im Idle = '{cs}', erwartet '1'"

    dut.uio_in.value = MODE
    await ClockCycles(dut.clk, 2)
    dut.uio_in.value = MODE | (1 << START_BIT)
    await ClockCycles(dut.clk, 1)
    dut.uio_in.value = MODE

    mosi = sck = cs_low = False
    for _ in range(40):
        await RisingEdge(dut.clk)
        mosi |= out_bit(dut.uio_out, 0) == "1"
        sck |= out_bit(dut.uio_out, 2) == "1"
        cs_low |= out_bit(dut.uio_out, 3) == "0"
    assert sck, "SCK schwingt nie -> Taktausgang tot"
    assert mosi, "MOSI nie 1 -> 0x03 wird nicht gesendet"
    assert cs_low, "CS nie low -> SPI startet nicht"


@cocotb.test()
async def test_gaussian_pixel_matrices(dut):
    """MODE=0: 100 zufaellige 3x3-Patches durch die Faltung."""
    rng = random.Random(1234)
    start_clock(dut)
    await reset_dut(dut)
    for i in range(100):
        pixels = [rng.randint(0, 255) for _ in range(NUM_PIXELS)]
        actual = await run_one_matrix(dut, pixels)
        expected = sum(p * w for p, w in zip(pixels, FILTER))
        assert actual == expected, f"Matrix {i+1}: erwartet {expected}, bekam {actual} (pixels={pixels})"
        await reset_dut(dut)


@cocotb.test()
async def test_spi_hdc(dut):
    """MODE=1: SPI liest R0..R3, HDC = (R0^R1) & (R3^R2)."""
    rng = random.Random(7)
    start_clock(dut)
    await reset_dut(dut)
    vectors = [[0xB3, 0x5C, 0x12, 0xFF]] + [[rng.randint(0, 255) for _ in range(4)] for _ in range(20)]
    for r in vectors:
        actual = await spi_read_hdc(dut, r)
        expected = hdc_expected(r)
        assert actual == expected, f"R={[hex(x) for x in r]}: erwartet 0x{expected:02x}, bekam 0x{actual:02x}"
        await reset_dut(dut)
