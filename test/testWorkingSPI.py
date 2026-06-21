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
#   BUNDLE = (R0 ^ R1) & (R3 ^ R2)  -> auf uo_out.

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge, Timer


FILTER = [1, 2, 1, 2, 4, 2, 1, 2, 1]   # palindromisch -> Register i hat Gewicht FILTER[i]
NUM_PIXELS = 9
ENABLE_CYCLES = 9                       # Bitebenen-Counter 0..7 -> 8 Schritte (+1 Reserve)

# Bit-Positionen in uio_in
MODE_BIT, OUTSEL1, OUTSEL0, WRITE_BIT, EN_BIT = 7, 6, 5, 4, 1
START_BIT, MISO_BIT = 4, 1              # im SPI-Mode teilen sich write/START bzw. en/MISO die Pins
MODE = 1 << MODE_BIT


# ---------------------------------------------------------------- Clock
_first_clock = True


async def ensure_clock(dut):
    """Startet PRO Test einen frischen Takt (cocotb beendet Tasks zwischen Tests,
    daher braucht jeder Test seinen eigenen Clock-Task).
    Nur beim ALLERERSTEN Mal: Eingaenge auf 0 treiben und via Timer wirksam machen,
    BEVOR die erste Taktflanke kommt -- sonst latcht der reset-lose SPIReader beim
    Kaltstart RUN=X ein (CS/SCK dann dauerhaft X). Ab dem 2. Test sind Eingaenge und
    Flipflops bereits definiert, da reicht ein normaler Clock-Start."""
    global _first_clock
    if _first_clock:
        dut.ena.value = 1
        dut.ui_in.value = 0
        dut.uio_in.value = 0
        dut.rst_n.value = 0
        await Timer(1, unit="ns")      # Eingaenge anlegen, noch KEINE Taktflanke
        _first_clock = False
    cocotb.start_soon(Clock(dut.clk, 10, unit="us").start())


def out_bit(sig, idx: int) -> str:
    """Liest Bit idx (0=LSB) eines Busses als '0'/'1'/'x'. EINDEUTIG ueber
    to_unsigned()+Shift (keine Endianness-/str-Reihenfolge-Falle); faellt bei
    X/Z im Bus auf LogicArray-Indexierung zurueck."""
    v = sig.value
    try:
        return "1" if ((v.to_unsigned() >> idx) & 1) else "0"
    except Exception:
        try:
            return str(v[idx]).lower()
        except Exception:
            return "?"


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
    """HDC_Calc-Verdrahtung (Stand nach Umbau): BUNDLE = (R0 ^ R1) & (R3 ^ R2)."""
    assert len(r) == 4
    return (r[0] ^ r[1]) & (r[3] ^ r[2])


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
    """MODE=1 (uio7): SPI-Reader treiben und uo_out (=HDC_Out) lesen.

    Ablauf wie in der Digital-Schaltung:
      uio7=1  ->  START-Puls (uio4) genau 1 Takt  ->  START wieder aus
      ->  56 SCK MISO einspeisen (interner CLK = 2x SCK -> 112 Takte)
      ->  reichlich nachtakten bis DONE sicher anliegt (~130 Takte), dann uo lesen.
    """
    assert len(r_bytes) == 4
    # uio7=1 stabil setzen (nach reset_dut war MODE=0) und kurz settlen lassen
    dut.uio_in.value = MODE
    await ClockCycles(dut.clk, 2)
    # START: uio4=1 fuer genau 1 Takt, dann wieder aus
    dut.uio_in.value = MODE | (1 << START_BIT)
    await ClockCycles(dut.clk, 1)
    dut.uio_in.value = MODE
    # 56 SCK: 24x cmd+addr (MISO egal) + 32 Datenbits (R0..R3, MSB-first), je 2 Takte
    miso_bits = [0] * 24 + [(b >> p) & 1 for b in r_bytes for p in range(7, -1, -1)]
    for bit in miso_bits:
        dut.uio_in.value = MODE | (bit << MISO_BIT)
        await ClockCycles(dut.clk, 2)
    # Reserve takten bis DONE sicher anliegt; MISO egal, Schieberegister friert ein
    dut.uio_in.value = MODE
    await ClockCycles(dut.clk, 20)
    return int(dut.uo_out.value) & 0xFF


# ---------------------------------------------------------------- Tests
@cocotb.test()
async def test_spi_basic_outputs(dut):
    """Simpelster Output-Lebenszeichen-Test (keine Daten-Pruefung):
       1) CS muss von Anfang an HIGH sein (idle, deasserted).
       2) Nach START muss MOSI irgendwann 1 werden (es wird 0x03 gesendet).
       3) Nach START muss SCK irgendwann anschwingen (Takt nach aussen).
    Liest dut.uio_out X-tolerant Bit fuer Bit. Laeuft als ERSTER Test, damit die
    SPI im frischen Init-Zustand ist."""
    await ensure_clock(dut)
    await reset_dut(dut)

    # --- 1) CS im Idle (Rohwerte zur Diagnose mitloggen) ---
    cs_idle = out_bit(dut.uio_out, 3)
    dut._log.info(f"DIAG idle: uio_oe={dut.uio_oe.value!r}  uio_out={dut.uio_out.value!r}  "
                  f"-> CS(idle)={cs_idle}  SCK={out_bit(dut.uio_out,2)}  MOSI={out_bit(dut.uio_out,0)}")

    # --- SPI-Mode + ein START-Puls ---
    dut.uio_in.value = MODE                       # uio7=1
    await ClockCycles(dut.clk, 2)
    dut.uio_in.value = MODE | (1 << START_BIT)    # START
    await RisingEdge(dut.clk)
    dut.uio_in.value = MODE                        # startSPI wieder aus

    # --- 2)+3) 40 Takte beobachten (MISO egal, wir testen nur die Ausgaenge) ---
    mosi_seen_1 = False
    sck_seen_1 = False
    cs_seen_0 = False
    for c in range(40):
        await RisingEdge(dut.clk)
        m = out_bit(dut.uio_out, 0)   # MOSI
        s = out_bit(dut.uio_out, 2)   # SCK
        cs = out_bit(dut.uio_out, 3)  # CS
        mosi_seen_1 |= (m == "1")
        sck_seen_1 |= (s == "1")
        cs_seen_0 |= (cs == "0")
        dut._log.info(f"  cyc {c:2d}: MOSI={m} SCK={s} CS={cs}")

    # Auswertung am ENDE, damit das komplette Log immer sichtbar ist
    dut._log.info(f"Ergebnis: CS_idle={cs_idle}  MOSI_war_1={mosi_seen_1}  "
                  f"SCK_war_1={sck_seen_1}  CS_war_0={cs_seen_0}")
    assert cs_idle == "1", f"CS im Idle = '{cs_idle}', erwartet '1' (siehe DIAG-Zeile oben)"
    assert sck_seen_1, "SCK ging nach START nie auf 1 -> Takt-Ausgang funktioniert nicht"
    assert mosi_seen_1, "MOSI war nie 1 -> 0x03-Kommando wird nicht gesendet"
    assert cs_seen_0, "CS ging nach START nie low -> SPI startet nicht"
    dut._log.info("Basis-Outputs OK: CS idle high, SCK schwingt, MOSI sendet (0x03), CS aktiv.")


@cocotb.test()
async def test_gaussian_pixel_matrices(dut):
    """MODE=0: 100 zufaellige 3x3-Patches durch die Faltung."""
    NUM_MATRICES = 100
    SEED = 1234
    rng = random.Random(SEED)

    await ensure_clock(dut)
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


@cocotb.test()
async def test_spi_hdc(dut):
    """MODE=1: SPI liest R0..R3, HDC rechnet BUNDLE = (R0^R1) & (R3^R2)."""
    NUM_VEC = 20
    SEED = 7
    rng = random.Random(SEED)

    await ensure_clock(dut)
    await reset_dut(dut)

    dut._log.info(f"SPI+HDC: {NUM_VEC} zufaellige R0..R3-Saetze (seed={SEED})")

    # fester Referenzvektor (B3,5C,12,FF -> (B3^5C)&(FF^12) = 0xED)
    vectors = [[0xB3, 0x5C, 0x12, 0xFF]] + [
        [rng.randint(0, 255) for _ in range(4)] for _ in range(NUM_VEC)
    ]

    for n, r in enumerate(vectors):
        actual = await spi_read_hdc(dut, r)
        expected = hdc_expected(r)
        dut._log.info(f"[{n + 1:2d}] R={[hex(x) for x in r]} "
                      f"expected=0x{expected:02x} actual=0x{actual:02x}")
        assert actual == expected, (
            f"HDC falsch fuer R={[hex(x) for x in r]}: "
            f"expected=0x{expected:02x}, got=0x{actual:02x}")
        await reset_dut(dut)        # SPI-Schieberegister fuer naechsten Read leeren

    dut._log.info(f"Alle {len(vectors)} SPI+HDC-Saetze korrekt.")
