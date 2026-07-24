#!/bin/sh
root_dir="[YOUR PATH]"
"${root_dir}/bin/julia" --threads 16 "${root_dir}/jl/ac_e1201.jl" public private
python py/ac_control.py public private
