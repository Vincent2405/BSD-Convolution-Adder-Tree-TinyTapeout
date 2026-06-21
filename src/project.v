/*
 * Copyright (c) 2024 Your Name
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

module tt_um_Vincent2405_adder_tree (
    input  wire [7:0] ui_in,
    output wire [7:0] uo_out,
    input  wire [7:0] uio_in,
    output wire [7:0] uio_out,
    output wire [7:0] uio_oe,
    input  wire       ena,
    input  wire       clk,
    input  wire       rst_n
);

  wire rst = ~rst_n;

  
  wire mosi, sck, cs;

  TinyTapeoutAdderTreeMitSPI_HDC core (
    .ui_in   (ui_in),
    .clk     (clk),
    .rst     (rst),
    .\[uio1]  (uio_in[1]),   // en / MISO
    .\[uio4]  (uio_in[4]),   // write / START
    .\[uio5]  (uio_in[5]),   // outSel[0]
    .\[uio6]  (uio_in[6]),   // outSel[1]
    .\[uio7]  (uio_in[7]),   // MODE (0=Faltung, 1=SPI+HDC)
    .uo_out  (uo_out),
    .\[uio0]  (mosi),        // MOSI
    .\[uio2]  (sck),         // SCK
    .\[uio3]  (cs)           // CS
  );

  assign uio_out[0]   = mosi;
  assign uio_out[1]   = 1'b0;
  assign uio_out[2]   = sck;
  assign uio_out[3]   = cs;
  assign uio_out[7:4] = 4'b0000;

  assign uio_oe = 8'b0000_1101;

  wire _unused = &{ena, uio_in[0], uio_in[2], uio_in[3], 1'b0};

endmodule

`default_nettype wire