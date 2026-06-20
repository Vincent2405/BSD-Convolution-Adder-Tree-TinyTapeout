# BSD Convolution Adder Tree — Testbench

cocotb testbench for the **BSD Convolution Adder Tree** Tiny Tapeout project — a
hardware **3×3 Gaussian convolution** that works entirely in **Binary Signed Digit (BSD)**
arithmetic.

## What the design does

The chip convolves a 3×3 image patch with a fixed Gaussian kernel `[1 2 1; 2 4 2; 1 2 1]`,
fully on-chip:

1. The 9 raw 8-bit pixels of the patch are written into registers **R0–R8**.
2. For each of the 8 bit positions, one bit from each pixel forms a **9-bit address** into
   an on-chip **512×5 ROM** that holds the *preadded* kernel weight sums.
3. The 8 partial results are weighted by `2^(bit position)` and accumulated in a **BSD
   adder tree** (`BSD+TC → BSD` and `BSD+BSD → BSD`).
4. The result is output in BSD format:

   ```
   Y = Σ  ROM(bitplane_b) · 2^b      = Gaussian convolution of the patch
   ```

Signed-Digit encoding (2 bits/digit): `00 = -1`, `01 = 0`, `10 = 0`, `11 = +1`.

## What the test does

[`test.py`](test.py) drives the DUT through the full multiplexed protocol and checks the
result against a Python reference Gaussian:

1. Write 9 random pixels into R0–R8 (`uio_in[7]=WRITE`, `uio_in[3:0]=regSel`).
2. Run the convolution: hold `uio_in[6]=EN` for 8 clock cycles (bit-plane counter 0..7).
3. Read the 28-bit BSD result in four 8-bit chunks (`uio_in[5:4]=chunk`), decode it, and
   assert `decoded == Σ pixel · weight`.

Pin map of `uio_in[7:0] = [WRITE, EN, outSel1, outSel0, regSel3..0]`.

---

# Sample testbench for a Tiny Tapeout project

This is a sample testbench for a Tiny Tapeout project. It uses [cocotb](https://docs.cocotb.org/en/stable/) to drive the DUT and check the outputs.
See below to get started or for more information, check the [website](https://tinytapeout.com/hdl/testing/).

## Setting up

1. Edit [Makefile](Makefile) and modify `PROJECT_SOURCES` to point to your Verilog files.
2. Edit [tb.v](tb.v) and replace `tt_um_example` with your module name.

## How to run

To run the RTL simulation:

```sh
make -B
```

To run gatelevel simulation, first harden your project and copy `../runs/wokwi/results/final/verilog/gl/{your_module_name}.v` to `gate_level_netlist.v`.

Then run:

```sh
make -B GATES=yes
```

If you wish to save the waveform in VCD format instead of FST format, edit tb.v to use `$dumpfile("tb.vcd");` and then run:

```sh
make -B FST=
```

This will generate `tb.vcd` instead of `tb.fst`.

## How to view the waveform file

Using GTKWave

```sh
gtkwave tb.fst tb.gtkw
```

Using Surfer

```sh
surfer tb.fst
```