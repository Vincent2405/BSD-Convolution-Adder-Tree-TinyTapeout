# SPDX-FileCopyrightText: © 2024 Tiny Tapeout
# SPDX-License-Identifier: Apache-2.0

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles


FILTER = [
    1, 2, 1,
    2, 4, 2,
    1, 2, 1
]


def decode_bsd_digit(two_bits: int) -> int:
    if two_bits == 0b00:
        return -1
    if two_bits == 0b01:
        return 0
    if two_bits == 0b10:
        return 0
    if two_bits == 0b11:
        return 1

    raise ValueError(f"Invalid BSD digit: {two_bits}")


def decode_bsd_value(raw: int, digits: int) -> int:
    value = 0

    for i in range(digits):
        digit_bits = (raw >> (2 * i)) & 0b11
        digit = decode_bsd_digit(digit_bits)
        value += digit * (1 << i)

    return value


def make_write_select(register_index: int) -> int:
    assert 0 <= register_index <= 7

    write_enable = 1 << 7
    register_select = register_index & 0b111

    return write_enable | register_select


def make_read_select(chunk_index: int) -> int:
    assert 0 <= chunk_index <= 3

    return (chunk_index & 0b11) << 3


def gaussian_expected(pixels: list[int]) -> int:
    assert len(pixels) == 9

    for p in pixels:
        assert 0 <= p <= 255

    return sum(p * w for p, w in zip(pixels, FILTER))


def pixels_to_memory_addresses(pixels: list[int]) -> list[int]:
    assert len(pixels) == 9

    for p in pixels:
        assert 0 <= p <= 255

    addresses = []

    for bit in range(8):
        addr = 0

        for j in range(9):
            bit_value = (pixels[j] >> bit) & 1
            addr |= bit_value << j

        addresses.append(addr)

    return addresses


def preadded_rom_value_from_address(addr: int, filter_values=FILTER) -> int:
    assert 0 <= addr < 512
    assert len(filter_values) == 9

    total = 0

    for j in range(9):
        if ((addr >> j) & 1) == 1:
            total += filter_values[j]

    return total


def pixels_to_preadded_rom_values(pixels: list[int]) -> list[int]:
    addresses = pixels_to_memory_addresses(pixels)

    rom_values = [
        preadded_rom_value_from_address(addr)
        for addr in addresses
    ]

    return rom_values


def expected_from_preadded_values(input_values: list[int]) -> int:
    assert len(input_values) == 8

    return sum(input_values[i] << i for i in range(8))


def random_pixels(rng: random.Random) -> list[int]:
    return [rng.randint(0, 255) for _ in range(9)]


async def reset_dut(dut):
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    dut.rst_n.value = 0

    await ClockCycles(dut.clk, 10)

    dut.rst_n.value = 1

    await ClockCycles(dut.clk, 1)


async def run_one_matrix(dut, pixels: list[int], BSD_DIGITS: int = 14) -> int:
    """Lädt eine 3x3-Matrix in die Register, liest das BSD-Ergebnis aus und
    gibt den dekodierten Wert zurück."""

    input_values = pixels_to_preadded_rom_values(pixels)

    expected_direct = gaussian_expected(pixels)
    expected_regs = expected_from_preadded_values(input_values)

    assert expected_direct == expected_regs, (
        f"Preadd mismatch: direct={expected_direct}, regs={expected_regs}, "
        f"input_values={input_values}, pixels={pixels}"
    )

    # Register R0..R7 mit den preadded-Werten laden
    for reg in range(8):
        dut.ui_in.value = input_values[reg] & 0xFF
        dut.uio_in.value = make_write_select(reg)
        await ClockCycles(dut.clk, 1)

    # Schreiben deaktivieren
    dut.uio_in.value = 0b0000_0000
    await ClockCycles(dut.clk, 1)
    await ClockCycles(dut.clk, 2)

    # BSD-Ergebnis in vier 8-Bit-Chunks aus uo_out lesen
    raw_bsd = 0
    chunks = []

    for chunk in range(4):
        dut.uio_in.value = make_read_select(chunk)
        await ClockCycles(dut.clk, 1)

        chunk_value = int(dut.uo_out.value) & 0xFF
        chunks.append(chunk_value)
        raw_bsd |= chunk_value << (8 * chunk)

    actual = decode_bsd_value(raw_bsd, BSD_DIGITS)

    return actual, expected_direct, raw_bsd, chunks, input_values


@cocotb.test()
async def test_gaussian_random_matrices(dut):
    NUM_MATRICES = 100
    SEED = 1234

    rng = random.Random(SEED)

    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    await reset_dut(dut)

    dut._log.info(
        f"Teste {NUM_MATRICES} zufällige Matrizen (seed={SEED}), "
        f"FILTER={FILTER}"
    )

    for i in range(NUM_MATRICES):
        pixels = random_pixels(rng)

        actual, expected, raw_bsd, chunks, input_values = await run_one_matrix(
            dut, pixels
        )

        dut._log.info(
            f"[{i + 1:3d}/{NUM_MATRICES}] pixels={pixels} "
            f"expected={expected} actual={actual}"
        )

        assert actual == expected, (
            f"Matrix {i + 1}/{NUM_MATRICES} falsch: "
            f"expected={expected}, got={actual}. "
            f"pixels={pixels}, input_values={input_values}, "
            f"raw_bsd=0x{raw_bsd:08x}, raw_bsd=0b{raw_bsd:032b}, "
            f"chunks={[hex(c) for c in chunks]}"
        )

        # Vor der nächsten Matrix den DUT zurücksetzen, damit jede Matrix
        # mit definierten/initialen Registerwerten startet.
        await reset_dut(dut)

    dut._log.info(f"Alle {NUM_MATRICES} Matrizen korrekt.")
