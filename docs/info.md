<!---

This file is used to generate your project datasheet. Please fill in the information below and delete any unused
sections.

You can also include images in this folder and reference them in the markdown. Each image must be less than
512 kb in size, and the combined size of all images must be less than 1 MB.
-->

## How it works

This chip has **two modes**, selected by `uio_in[7]` (MODE):

- **MODE = 0 — Convolution:** a 3×3 Gaussian convolution of an image patch, computed
  fully on-chip with 512*5 bit ROM and a **Binary Signed Digit (BSD)**
  adder tree.
- **MODE = 1 — SPI + HDC:** an on-chip SPI master reads four bytes from an external SPI
  RAM, and a small **Hyperdimensional Computing** core binds & bundles them.

`uio` pins are dual-use; `uio_oe = 0b0000_1101` (bits 0/2/3 driven as outputs).

```
uio_in[7]   => MODE        (0 = Convolution, 1 = SPI + HDC)
uio_in[6:5] => outSel       | (unused in SPI mode)        [MODE 0]
uio_in[4]   => WRITE        | START                       [write / start]
uio_in[1]   => EN           | MISO                        [run / spi-in]
uio[0/2/3]  => MOSI / SCK / CS  (SPI outputs, MODE 1)
```

---

## MODE 0 — Convolution

**Signed-Digit (SD) format** — two bits per digit:

```
00 => -1     01 => 0     10 => 0     11 => +1
```

**Data flow:**

1. The 9 pixels of a 3×3 patch are written into registers **R0–R8** (8-bit each):

   ```
   [ R0  R1  R2 ]
   [ R3  R4  R5 ]
   [ R6  R7  R8 ]
   ```

2. The computation runs over the **8 bit positions** of the pixels. For each bit
   position, one bit is taken from each of the 9 pixels to form a **9-bit address** into
   an on-chip **512×5 ROM** that stores the *preadded* weight sums of the fixed kernel
   (Gaussian `[1 2 1; 2 4 2; 1 2 1]`), giving a **5-bit partial value** per bit position.

3. Each partial value is weighted by `2^(bit position)` and accumulated. Every addition
   is performed in **BSD** (`BSD + TC => BSD` or `BSD + BSD => BSD`):

   resulting in scalar of filter kernel with corresponding R0...R8 pixel inputs
  

4. The result `Y` is provided in **BSD format** (28 bits = 14 SD digits).

You load the **raw 8-bit pixels** — the ROM does the kernel weighting on-chip. For a
different fixed kernel, only the 512×5 ROM contents change, not the datapath (Gaussian Rom values are Hardcoded on the chip so cant be changed for now).

---

## MODE 1 — SPI + HDC

The SPI master (Mode 0, MSB-first) reads **4×8 bit** (`R0..R3`) from an external SPI RAM
(23LC512 / RP2040 `spi-ram-emu`): it drives `CS` low, sends `READ = 0x03` + a 16-bit
address (`0x0000`), then clocks in the four data bytes on `MISO`. `SCK` runs at **half**
the chip clock (one SPI bit = 2 chip clocks), so a full read is **56 SCK = 112 clocks**.

The HDC core then computes, bitwise (binding = XOR, 2-bundle = AND):

```
BUNDLE = (R0 XOR R1) AND (R2 XOR R3)   ->  uo_out
```

---

## How to test — MODE 0 (Convolution)

`uio_in[7] = 0`. The register write pointer **auto-increments**, so just write the 9
pixels in order — no register index needed.

### 1) Write the 9 pixels

For each pixel: put it on `ui_in`, set `uio_in = 0x10` (WRITE = 1, EN = 0), one clock.

Example pixels `[225, 59, 3, 46, 17, 42, 50, 181, 121]` (expected result **1123**):

```
ui_in = 225   uio_in = 0x10   -> clock   (R0)
ui_in =  59   uio_in = 0x10   -> clock   (R1)
ui_in =   3   uio_in = 0x10   -> clock   (R2)
...
ui_in = 121   uio_in = 0x10   -> clock   (R8)
```

### 2) Run the convolution

Hold `uio_in = 0x02` (EN = 1) and apply **8 clock cycles** — the counter steps
through positions 0..7 and fills the BSD adder tree inputs with the precalculated rom values. 
Note: with 8 lane parallel ROM this step could be computed in 1 cycle but would require much more Gates.

### 3) Read the result

28-bit BSD result in four 8-bit chunks on `uo_out`, selected by `uio_in[6:5]`
(WRITE = 0, EN = 0):

```
uio_in = 0x00  => uo_out = o0  (bits  7:0)
uio_in = 0x20  => uo_out = o1  (bits 15:8)
uio_in = 0x40  => uo_out = o2  (bits 23:16)
uio_in = 0x60  => uo_out = o3  (bits 31:24, top nibble is a 0101 marker)
```

Reconstruct and decode (2 bits = 1 SD digit, 14 digits):

```
result = [ o3 | o2 | o1 | o0 ] 
```

## How to test — MODE 1 (SPI + HDC)

`uio_in[7] = 1`. On the demo board, `MOSI/SCK/CS` (uio 0/2/3) go to the RAM and `MISO`
(uio 1) comes back; in simulation the testbench plays the RAM.

```
uio_in = 0x80                 // MODE = 1, idle
uio_in = 0x90  -> clock       // START pulse (1 clock), then back to 0x80
... 56 SCK (112 clocks): SPI sends 0x03 + address, reads R0..R3 on MISO ...
read uo_out                   // = HDC result = (R0^R1) & (R3^R2)
```
address is due to simplicity hardcoded to 0x0. therefore the SPI ram should have its 32 bit (v0..v3) at position 0x0

ram only reads 32 bit from spi at adress 0x0 these 32 bit get decodet to v0...v3 and are stored in R0...R3

Example: `R0..R3 = 0xB3, 0x5C, 0x12, 0xFF`
→ `(0xB3 ^ 0x5C) & (0xFF ^ 0x12) = 0xEF & 0xED = 0xED`.
