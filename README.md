![](../../workflows/gds/badge.svg) ![](../../workflows/docs/badge.svg) ![](../../workflows/test/badge.svg) ![](../../workflows/fpga/badge.svg)

# BSD Convolution Adder Tree + SPI / HDC

A Tiny Tapeout chip with **two modes**, selected by `uio_in[7]` (MODE):

- **MODE = 0 — Convolution:** a 3×3 Gaussian convolution of an image patch, computed
  entirely on-chip and fully in **Binary Signed Digit (BSD)** arithmetic.
- **MODE = 1 — SPI + HDC:** an SPI master reads four bytes from an external SPI RAM and a
  small **Hyperdimensional Computing** core binds & bundles them.

- [Read the project documentation](docs/info.md)
- Circuits are in `docs/DigitalSimSchaltungen` (TinyTapeoutAdderTree.dig)(built in [hneemann/Digital](https://github.com/hneemann/Digital)).

## MODE 0 — Convolution

Load the **9 raw 8-bit pixels** of a 3×3 patch into registers `R0–R8`; the chip returns
the convolved value in BSD format.

```
[ R0 R1 R2 ]
[ R3 R4 R5 ]   --(EN, 8 clocks)-->   Y = sum(filter[i,j] * w[i,j])
[ R6 R7 R8 ]
```

For each of the 8 bit positions, one bit from each of the 9 pixels forms a **9-bit
address** into an on-chip **512×5 ROM** that holds the *preadded* sums of the fixed
kernel `[1 2 1; 2 4 2; 1 2 1]`. The 8 partial values are weighted by `2^b` and accumulated
in a **BSD adder tree**. 

Signed-Digit encoding (2 bits/digit): `00 = -1`, `01 = 0`, `10 = 0`, `11 = +1`.

The register write pointer **auto-increments** — you just write the 9 pixels in order,
no register index needed.

## MODE 1 — SPI + HDC

An SPI master (Mode 0, MSB-first) reads **4×8 bit** (`R0..R3`) from an external SPI RAM
(23LC512 / RP2040 `spi-ram-emu`) at adress 0x0: it sends `READ 0x03` + 0x0 and clocks in
the four bytes. The HDC core then computes, bitwise:

```
BUNDLE = (R0 XOR R1) & (R3 XOR R2)        (bind = XOR, bundle = AND)
```
on `uo_out`. The SPI clock `SCK` runs at half the chip clock (one bit = 2 clocks).

## Pin map

`uio` pins are dual-use depending on MODE; `uio_oe = 0b0000_1101` (bits 0/2/3 are outputs).

| pin | MODE 0 (Convolution) | MODE 1 (SPI + HDC) |
|-----|----------------------|---------------------|
| `ui_in[7:0]`  | pixel value (input)        | – |
| `uo_out[7:0]` | BSD result chunk (output)  | HDC result (output) |
| `uio[7]` | MODE = 0 | MODE = 1 |
| `uio[6:5]` | outSel (read chunk) | – |
| `uio[4]` | WRITE (in) | START (in) |
| `uio[3]` | – | CS (out) |
| `uio[2]` | – | SCK (out) |
| `uio[1]` | EN (in) | MISO (in) |
| `uio[0]` | – | MOSI (out) |

## How to test

- **MODE 0:** write 9 pixels (`uio=0x10`, one clock each → R0..R8), run (`uio=0x02`,
  ~8 clocks), read 4 BSD chunks (`uio = chunk<<5`) on `uo_out`, decode the 14 SD digits.
- **MODE 1:** pulse START (`uio=0x90`, 1 clock), feed MISO on `uio[1]` while clocking the
  56 SCK, then read `uo_out` (= HDC result).

see [docs/info.md](docs/info.md). 

---

## What is Tiny Tapeout?

Tiny Tapeout is an educational project that aims to make it easier and cheaper than ever to get your digital and analog designs manufactured on a real chip.

To learn more and get started, visit https://tinytapeout.com.

## Set up your Verilog project

1. Add your Verilog files to the `src` folder.
2. Edit the [info.yaml](info.yaml) and update information about your project, paying special attention to the `source_files` and `top_module` properties. If you are upgrading an existing Tiny Tapeout project, check out our [online info.yaml migration tool](https://tinytapeout.github.io/tt-yaml-upgrade-tool/).
3. Edit [docs/info.md](docs/info.md) and add a description of your project.
4. Adapt the testbench to your design.

The GitHub action will automatically build the ASIC files using [LibreLane](https://www.zerotoasiccourse.com/terminology/librelane/).

## Enable GitHub actions to build the results page

- [Enabling GitHub Pages](https://tinytapeout.com/faq/#my-github-action-is-failing-on-the-pages-part)

## Resources

- [FAQ](https://tinytapeout.com/faq/)
- [Digital design lessons](https://tinytapeout.com/digital_design/)
- [Learn how semiconductors work](https://tinytapeout.com/siliwiz/)
- [Join the community](https://tinytapeout.com/discord)
- [Build your design locally](https://www.tinytapeout.com/guides/local-hardening/)

## What next?

- [Submit your design to the next shuttle](https://app.tinytapeout.com/).
- Edit [this README](README.md) and explain your design, how it works, and how to test it.
- Share your project on your social network of choice:
  - LinkedIn [#tinytapeout](https://www.linkedin.com/search/results/content/?keywords=%23tinytapeout) [@TinyTapeout](https://www.linkedin.com/company/100708654/)
  - Mastodon [#tinytapeout](https://chaos.social/tags/tinytapeout) [@matthewvenn](https://chaos.social/@matthewvenn)
  - X (formerly Twitter) [#tinytapeout](https://twitter.com/hashtag/tinytapeout) [@tinytapeout](https://twitter.com/tinytapeout)
  - Bluesky [@tinytapeout.com](https://bsky.app/profile/tinytapeout.com)
