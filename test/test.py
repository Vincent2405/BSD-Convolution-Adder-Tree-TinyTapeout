# SPDX-FileCopyrightText: © 2024 Tiny Tapeout
# SPDX-License-Identifier: Apache-2.0

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


async def reset_dut(dut):
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    dut.rst_n.value = 0

    await ClockCycles(dut.clk, 10)

    dut.rst_n.value = 1

    await ClockCycles(dut.clk, 1)

@cocotb.test()
async def test_gaussian_pixels_bsd_result(dut):
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    await reset_dut(dut)

    pixels = [
        1, 2, 3,
        4, 255, 6,
        7, 8, 10
    ]

    input_values = pixels_to_preadded_rom_values(pixels)

    expected_direct = gaussian_expected(pixels)
    expected_regs = expected_from_preadded_values(input_values)

    dut._log.info(f"pixels          = {pixels}")
    dut._log.info(f"FILTER          = {FILTER}")
    dut._log.info(f"input_values    = {input_values}")
    dut._log.info(f"expected_direct = {expected_direct}")
    dut._log.info(f"expected_regs   = {expected_regs}")

    assert expected_direct == expected_regs, (
        f"Preadd mismatch: direct={expected_direct}, regs={expected_regs}, "
        f"input_values={input_values}"
    )


    dut._log.info("Loading registers R0..R7 with preadded values")

    for reg in range(8):
        dut.ui_in.value = input_values[reg] & 0xFF
        dut.uio_in.value = make_write_select(reg)

        await ClockCycles(dut.clk, 1)

        dut._log.info(
            f"write reg={reg}, "
            f"ui_in=0b{input_values[reg]:08b}, "
            f"uio_in=0b{int(dut.uio_in.value):08b}, "
            f"write_enable={(int(dut.uio_in.value) >> 7) & 1}, "
            f"uo_out={str(dut.uo_out.value)}"
        )


    dut.uio_in.value = 0b0000_0000
    await ClockCycles(dut.clk, 1)

    dut._log.info(
        f"write disabled, uio_in=0b{int(dut.uio_in.value):08b}"
    )

    await ClockCycles(dut.clk, 2)

    raw_bsd = 0
    chunks = []

    dut._log.info("Reading BSD result in four 8-bit chunks from uo_out")

    for chunk in range(4):
        dut.uio_in.value = make_read_select(chunk)

        await ClockCycles(dut.clk, 1)

        chunk_value = int(dut.uo_out.value) & 0xFF
        chunks.append(chunk_value)
        raw_bsd |= chunk_value << (8 * chunk)

        dut._log.info(
            f"read chunk={chunk}, "
            f"uio_in=0b{int(dut.uio_in.value):08b}, "
            f"write_enable={(int(dut.uio_in.value) >> 7) & 1}, "
            f"uo_out=0b{chunk_value:08b}, "
            f"uo_out=0x{chunk_value:02x}"
        )

    dut._log.info(
        "chunks low-to-high = "
        + " ".join(f"0x{x:02x}" for x in chunks)
    )

    dut._log.info(f"raw_bsd = 0x{raw_bsd:08x}")
    dut._log.info(f"raw_bsd = 0b{raw_bsd:032b}")

    BSD_DIGITS = 14
    actual = decode_bsd_value(raw_bsd, BSD_DIGITS)

    expected = expected_direct

    dut._log.info(f"actual decoded BSD = {actual}")
    dut._log.info(f"expected           = {expected}")

    assert actual == expected, (
        f"Wrong BSD result: expected {expected}, got {actual}. "
        f"pixels={pixels}, input_values={input_values}, "
        f"raw_bsd=0x{raw_bsd:08x}, "
        f"raw_bsd=0b{raw_bsd:032b}, "
        f"chunks={[hex(c) for c in chunks]}"
    )