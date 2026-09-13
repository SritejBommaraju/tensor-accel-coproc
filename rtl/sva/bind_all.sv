// Non-invasive bind points: rtl/pe.sv and rtl/systolic_array.sv are never edited.
bind pe pe_sva u_pe_sva (.*, .weight(weight));

// N=4 is hardcoded here (matches top.sv's default) because Verilator requires each per-PE
// register to be wired in explicitly as a bind port connection -- it won't resolve a downward
// hierarchical reference into a child instance's scope on its own.
bind systolic_array systolic_array_sva #(.N(N)) u_systolic_array_sva (
    .clk(clk), .rst(rst),
    .psum_wire(psum_wire), .act_wire(act_wire), .act_in(act_in),
    .weight_arr('{
        '{rows[0].cols[0].u_pe.weight, rows[0].cols[1].u_pe.weight, rows[0].cols[2].u_pe.weight, rows[0].cols[3].u_pe.weight},
        '{rows[1].cols[0].u_pe.weight, rows[1].cols[1].u_pe.weight, rows[1].cols[2].u_pe.weight, rows[1].cols[3].u_pe.weight},
        '{rows[2].cols[0].u_pe.weight, rows[2].cols[1].u_pe.weight, rows[2].cols[2].u_pe.weight, rows[2].cols[3].u_pe.weight},
        '{rows[3].cols[0].u_pe.weight, rows[3].cols[1].u_pe.weight, rows[3].cols[2].u_pe.weight, rows[3].cols[3].u_pe.weight}
    }),
    .weight_load_arr('{
        '{rows[0].cols[0].u_pe.weight_load, rows[0].cols[1].u_pe.weight_load, rows[0].cols[2].u_pe.weight_load, rows[0].cols[3].u_pe.weight_load},
        '{rows[1].cols[0].u_pe.weight_load, rows[1].cols[1].u_pe.weight_load, rows[1].cols[2].u_pe.weight_load, rows[1].cols[3].u_pe.weight_load},
        '{rows[2].cols[0].u_pe.weight_load, rows[2].cols[1].u_pe.weight_load, rows[2].cols[2].u_pe.weight_load, rows[2].cols[3].u_pe.weight_load},
        '{rows[3].cols[0].u_pe.weight_load, rows[3].cols[1].u_pe.weight_load, rows[3].cols[2].u_pe.weight_load, rows[3].cols[3].u_pe.weight_load}
    })
);
