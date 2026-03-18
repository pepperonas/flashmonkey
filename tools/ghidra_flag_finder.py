# -*- coding: utf-8 -*-
# Find where sys_stc+0x4a (lift_speed_limit flag) is set
# @category Navee
# @runtime Jython

program = currentProgram
listing = program.getListing()
memory = program.getMemory()
af = program.getAddressFactory().getDefaultAddressSpace()
decomp = ghidra.app.decompiler.DecompInterface()
decomp.openProgram(program)

print("=" * 60)
print("FINDING lift_speed_limit FLAG (sys_stc+0x4a)")
print("=" * 60)

# Find all writes to offset 0x4a
print("\n[1] Writes to +0x4a:")
instr_iter = listing.getInstructions(True)
writers = []
while instr_iter.hasNext() and not getMonitor().isCancelled():
    instr = instr_iter.next()
    s = str(instr)
    if "#0x4a" in s and ("str" in s):
        func = listing.getFunctionContaining(instr.getAddress())
        fname = func.getName() if func else "?"
        foffset = instr.getAddress().getOffset() - 0x08000000 + 0x10
        print("  %s @ %s [%s] FILE:0x%04X" % (s, instr.getAddress(), fname, foffset))
        if func:
            writers.append(func)

# Decompile writers
for func in writers[:5]:
    print("\n  === %s ===" % func.getName())
    results = decomp.decompileFunction(func, 30, getMonitor())
    if results and results.decompileCompleted():
        c = results.getDecompiledFunction().getC()
        lines = c.split("\n")
        for i, line in enumerate(lines):
            if "0x4a" in line or "lift" in line.lower() or "0x02" in line:
                for j in range(max(0,i-3), min(len(lines),i+4)):
                    m = ">>>" if j == i else "   "
                    print("    %s %s" % (m, lines[j]))
                print("    ---")

# Also check reads of 0x4a (to understand the flag values)
print("\n[2] Reads from +0x4a:")
instr_iter = listing.getInstructions(True)
while instr_iter.hasNext() and not getMonitor().isCancelled():
    instr = instr_iter.next()
    s = str(instr)
    if "#0x4a" in s and "ldr" in s:
        func = listing.getFunctionContaining(instr.getAddress())
        fname = func.getName() if func else "?"
        print("  %s @ %s [%s]" % (s, instr.getAddress(), fname))

decomp.dispose()
print("\nDone.")
