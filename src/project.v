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

  TinyTapeoutAdderTree core (
    .ui_in  (ui_in),
    .clk    (clk),
    .uio_in (uio_in),
    .rst    (rst),
    .uo_out (uo_out)
  );

  assign uio_out = 8'b0000_0000;
  assign uio_oe  = 8'b0000_0000;

  wire _unused = &{ena, 1'b0};

endmodule

`default_nettype wire