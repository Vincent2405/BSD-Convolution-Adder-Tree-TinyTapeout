![](../../workflows/gds/badge.svg) ![](../../workflows/docs/badge.svg) ![](../../workflows/test/badge.svg) ![](../../workflows/fpga/badge.svg)

# BSD Convolution Adder Tree

A Tiny Tapeout chip that computes a **3×3 Gaussian convolution** of an image patch,
entirely on-chip and fully in **Binary Signed Digit (BSD)** arithmetic.

- [Read the project documentation](docs/info.md)

## What it does

You load the **9 raw 8-bit pixels** of a 3×3 patch into registers `R0–R8`; the chip
returns the convolved value in BSD format.

```
[ R0 R1 R2 ]
[ R3 R4 R5 ]   --(EN, 8 clocks)-->   Y = Σ ROM(bitplane_b) · 2^b   (BSD)
[ R6 R7 R8 ]
```

How it works:
- [see info.md](docs/info.md)
- circuit can be found in docs/DigitalSimSchaltungen (top level circuit is TinyTapuoutAdderTree.dig)


Signed-Digit encoding (2 bits/digit): `00 = -1`, `01 = 0`, `10 = 0`, `11 = +1`.
Only the kernel changes for a different filter — the ROM contents, not the datapath.

## How to test

All I/O is multiplexed over `uio_in[7:0] = [WRITE, EN, outSel1, outSel0, regSel3..0]`:

| step | action | `uio_in` |
|------|--------|----------|
| **Write** | put pixel on `ui_in`, one clock per register | `1 0 00 <regSel 0..8>` |
| **Run**   | hold for **8 clocks** (bit-plane counter 0..7) | `0 1 00 0000` (`0x40`) |
| **Read**  | 28-bit BSD result in four 8-bit chunks on `uo_out` | `0 0 <chunk> 0000` |

[see info.md](docs/info.md)

---

## What is Tiny Tapeout?

Tiny Tapeout is an educational project that aims to make it easier and cheaper than ever to get your digital and analog designs manufactured on a real chip.

To learn more and get started, visit https://tinytapeout.com.

## Set up your Verilog project

1. Add your Verilog files to the `src` folder.
2. Edit the [info.yaml](info.yaml) and update information about your project, paying special attention to the `source_files` and `top_module` properties. If you are upgrading an existing Tiny Tapeout project, check out our [online info.yaml migration tool](https://tinytapeout.github.io/tt-yaml-upgrade-tool/).
3. Edit [docs/info.md](docs/info.md) and add a description of your project.
4. Adapt the testbench to your design. See [test/README.md](test/README.md) for more information.

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
