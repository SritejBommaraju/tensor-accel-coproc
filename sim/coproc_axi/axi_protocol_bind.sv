// Binds the unmodified sim/axi/axi_protocol_check.sv checker onto coproc_axi_sim_top's DUT
// boundary AXI signals (same checker module, new bind target -- axi_protocol_check.sv's own
// bind statements target stream_axi_top only, so they don't apply here).
bind coproc_axi_top axi_protocol_check #(.ID_W(4)) u_rd_check (
    .clk(clk), .rst(rst),
    .arvalid(m_arvalid), .arready(m_arready), .arlen(m_arlen),
    .rlast(m_rlast), .rvalid(m_rvalid), .rready(m_rready),
    .awvalid('0), .awready('0), .awlen('0),
    .wlast('0), .wvalid('0), .wready('0), .bvalid('0), .bready('0)
);

bind coproc_axi_top axi_protocol_check #(.ID_W(4)) u_wr_check (
    .clk(clk), .rst(rst),
    .arvalid('0), .arready('0), .arlen('0), .rlast('0), .rvalid('0), .rready('0),
    .awvalid(m_awvalid), .awready(m_awready), .awlen(m_awlen),
    .wlast(m_wlast), .wvalid(m_wvalid), .wready(m_wready), .bvalid(m_bvalid), .bready(m_bready)
);
