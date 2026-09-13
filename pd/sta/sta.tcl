# OpenSTA timing script. Env-var driven, same netlist/liberty for any module/N.
#
# Required env vars:
#   LIBERTY    sg13g2 liberty file
#   NETLIST    gate-level netlist (yosys write_verilog output)
#   TOP        top module name in the netlist
#   PERIOD_NS  clock period in ns for create_clock
# Optional:
#   CLK        clock port name (default clk)

read_liberty $::env(LIBERTY)
read_verilog $::env(NETLIST)
link_design $::env(TOP)

set clk_port [expr {[info exists ::env(CLK)] ? $::env(CLK) : "clk"}]
set period   $::env(PERIOD_NS)
set io_delay [expr {$period * 0.2}]

create_clock -name clk -period $period [get_ports $clk_port]
set_input_delay -clock clk $io_delay [all_inputs -no_clocks]
set_output_delay -clock clk $io_delay [all_outputs]

report_checks -path_delay max -digits 4
puts "---SUMMARY---"
report_wns
report_tns
report_worst_slack
