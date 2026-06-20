<!---

This file is used to generate your project datasheet. Please fill in the information below and delete any unused
sections.

You can also include images in this folder and reference them in the markdown. Each image must be less than
512 kb in size, and the combined size of all images must be less than 1 MB.
-->

## How it works

This project computes a **3×3 Gaussian convolution** of an image patch fully on-chip,
using bit-plane ROM decomposition and a **Binary Signed Digit (BSD)** adder tree.

**Signed-Digit (SD) format** — two bits per digit:

```
00 => -1
01 =>  0
10 =>  0
11 => +1
```

**Data flow:**

1. The 9 pixels of a 3×3 image patch are written into the registers **R0–R8** (8-bit each):

   ```
   [ R0  R1  R2 ]
   [ R3  R4  R5 ]
   [ R6  R7  R8 ]
   ```

2. The computation runs over the **8 bit positions** of the pixels. For each bit
   position, one bit is taken from each of the 9 pixels to form a **9-bit address**.
   This address indexes an **on-chip 512×5 ROM** that stores the *preadded* weight
   sums of the fixed 3×3 kernel (here Gaussian `[1 2 1; 2 4 2; 1 2 1]`), giving a
   **5-bit partial value** per bit position.

3. Each bit position's partial value is weighted by `2^(bit position)` and accumulated.
   Every addition is performed in **BSD format** (either `BSD + TC => BSD` or
   `BSD + BSD => BSD`).

   ```
   Y = Σ  ROM(bitplane_b) · 2^b      (b = 0 .. 7)
   ```

   which equals the full Gaussian convolution sum of the 3×3 patch.

4. The result `Y` is provided in **BSD format**.



## How to test

Tiny Tapeout provides only 8 dedicated input bits and 8 dedicated output bits, so the
register inputs and the result output are **multiplexed** via `uio_in`.

**Control signals on `uio_in`:**

```
uio_in[7]   => WRITE enable
uio_in[6]   => EN   (run the convolution / bit-plane counter)
uio_in[5:4] => output chunk select
uio_in[3:0] => register select (R0 .. R8)
```

### 1) Write the 9 pixels

For each pixel:

- Put the pixel value on `ui_in[7:0]`.
- Set `uio_in[7] = 1` (write enable), `uio_in[6] = 0` (EN off).
- Set `uio_in[3:0]` to the target register index.
- Apply one clock cycle.

Register selection:

```
uio_in[3:0] = 0000 => R0      uio_in[3:0] = 0101 => R5
uio_in[3:0] = 0001 => R1      uio_in[3:0] = 0110 => R6
uio_in[3:0] = 0010 => R2      uio_in[3:0] = 0111 => R7
uio_in[3:0] = 0011 => R3      uio_in[3:0] = 1000 => R8
uio_in[3:0] = 0100 => R4
```

Example pixels `[225, 59, 3, 46, 17, 42, 50, 181, 121]`:

```
ui_in  = 11100001   uio_in = 10000000   // write, R0   -> clock
ui_in  = 00111011   uio_in = 10000001   // write, R1   -> clock
ui_in  = 00000011   uio_in = 10000010   // write, R2   -> clock
ui_in  = 00101110   uio_in = 10000011   // write, R3   -> clock
ui_in  = 00010001   uio_in = 10000100   // write, R4   -> clock
ui_in  = 00101010   uio_in = 10000101   // write, R5   -> clock
ui_in  = 00110010   uio_in = 10000110   // write, R6   -> clock
ui_in  = 10110101   uio_in = 10000111   // write, R7   -> clock
ui_in  = 01111001   uio_in = 10001000   // write, R8   -> clock
```

### 2) Run the convolution (EN)

After all 9 registers are loaded, hold **`uio_in = 0100_0000` (EN = 1, WRITE = 0)**
and apply **8 clock cycles**. The internal bit-plane counter steps through all 8 bit
positions (0..7), performs the ROM lookups and fills the 8 internal partial registers;
the BSD adder tree then holds the final result.

```
uio_in = 01000000   // EN = 1
clock x8
```

### 3) Read the result

The BSD result is **28 bits** (14 SD digits), read in four 8-bit chunks on `uo_out[7:0]`,
selected by `uio_in[5:4]` (WRITE = 0, EN = 0):

```
uio_in = 00000000  => uo_out = o0  (bits  7:0)
uio_in = 00010000  => uo_out = o1  (bits 15:8)
uio_in = 00100000  => uo_out = o2  (bits 23:16)
uio_in = 00110000  => uo_out = o3  (bits 31:24, top nibble is a 0101 marker)
```

Reconstruct the raw value and decode (2 bits = 1 SD digit, 14 digits):

```
raw = [ o3 | o2 | o1 | o0 ]      // use the low 28 bits
Y   = Σ  SD(raw[2i+1:2i]) · 2^i  (i = 0 .. 13)
```

## Real convolution usage

For a real 3×3 image convolution you simply load the **raw 8-bit pixel values** of the
patch into R0–R8 — **no external preadd is needed anymore**; the on-chip 512×5 ROM does
the kernel weighting internally:

```
[p1 p2 p3]
[p4 p5 p6]   => load p1..p9 into R0..R8  =>  EN, 8 clocks  =>  read BSD result
[p7 p8 p9]
```

For each of the 8 bit positions, one bit from each of the 9 pixels forms a 9-bit ROM
address; the ROM returns the preadded kernel sum for that bit position. To use a
different fixed kernel (e.g. a sharpen or edge filter), only the 512×5 ROM contents
change — the datapath stays the same.