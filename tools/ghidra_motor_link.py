# -*- coding: utf-8 -*-
# Check if dashboard sends speed limit to motor controller
# @category Navee
# @runtime Jython

program = currentProgram
listing = program.getListing()
af = program.getAddressFactory().getDefaultAddressSpace()
decomp = ghidra.app.decompiler.DecompInterface()
decomp.openProgram(program)

print("=" * 60)
print("MOTOR CONTROLLER LINK ANALYSIS")
print("=" * 60)

# FUN_0800ad02 reads sys_stc+0x47 - what does it do with the value?
print("\n[1] FUN_0800ad02 - reads max_speed:")
func = listing.getFunctionAt(af.getAddress(0x0800ad02))
if func:
    results = decomp.decompileFunction(func, 30, getMonitor())
    if results and results.decompileCompleted():
        print(results.getDecompiledFunction().getC()[:4000])

# Check init function's full code to find where 22 vs 30 is decided
print("\n\n[2] FUN_0800e9d0 - full init (first 100 lines):")
func = listing.getFunctionAt(af.getAddress(0x0800e9d0))
if func:
    results = decomp.decompileFunction(func, 30, getMonitor())
    if results and results.decompileCompleted():
        c = results.getDecompiledFunction().getC()
        lines = c.split("\n")
        for line in lines[:100]:
            print("  %s" % line)

decomp.dispose()
print("\nDone.")
