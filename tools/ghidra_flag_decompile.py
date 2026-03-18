# -*- coding: utf-8 -*-
# @category Navee
# @runtime Jython

program = currentProgram
listing = program.getListing()
af = program.getAddressFactory().getDefaultAddressSpace()
decomp = ghidra.app.decompiler.DecompInterface()
decomp.openProgram(program)

# The strb at 0800f84a is in FUN_0800f9d0? That seems wrong (f84a < f9d0)
# Let's check what function actually contains 0800f84a
print("[1] Function containing 0x0800f84a:")
func = listing.getFunctionContaining(af.getAddress(0x0800f84a))
if func:
    print("  %s @ %s" % (func.getName(), func.getEntryPoint()))
    results = decomp.decompileFunction(func, 30, getMonitor())
    if results and results.decompileCompleted():
        c = results.getDecompiledFunction().getC()
        lines = c.split("\n")
        for i, line in enumerate(lines):
            if "0x4a" in line or "0x02" in line or "0x47" in line or "speed" in line.lower():
                for j in range(max(0,i-4), min(len(lines),i+5)):
                    m = ">>>" if j == i else "   "
                    print("    %s %s" % (m, lines[j]))
                print("    ---")

# Also disassemble around 0800f84a
print("\n[2] Disassembly around 0x0800f84a:")
for offset in range(-20, 30, 2):
    addr = af.getAddress(0x0800f84a + offset)
    instr = listing.getInstructionAt(addr)
    if instr:
        raw = ""
        for i in range(instr.getLength()):
            raw += "%02x " % (program.getMemory().getByte(addr.add(i)) & 0xFF)
        marker = " <<<" if offset == 0 or offset == 6 else ""
        print("  %s: %-16s %s%s" % (addr, raw.strip(), instr, marker))

# File offsets for patching
print("\n[3] PATCH POINTS:")
for addr_int, desc in [(0x0800f84a, "strb flag 0x4a (first)"), (0x0800f850, "strb flag 0x4a (second)")]:
    file_off = addr_int - 0x08000000 + 0x10
    print("  %s: 0x%08X -> FILE OFFSET 0x%04X" % (desc, addr_int, file_off))

decomp.dispose()
print("\nDone.")
