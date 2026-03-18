# -*- coding: utf-8 -*-
# Find where speed is CAPPED to 22
# @category Navee
# @runtime Jython

program = currentProgram
listing = program.getListing()
memory = program.getMemory()
af = program.getAddressFactory().getDefaultAddressSpace()
decomp = ghidra.app.decompiler.DecompInterface()
decomp.openProgram(program)

print("=" * 60)
print("FINDING SPEED CAP")
print("=" * 60)

# Find all ldrb instructions that read from offset 0x47
print("\n[1] All reads from struct+0x47:")
instr_iter = listing.getInstructions(True)
readers = set()
while instr_iter.hasNext() and not getMonitor().isCancelled():
    instr = instr_iter.next()
    s = str(instr)
    if "#0x47" in s and "ldr" in s:
        func = listing.getFunctionContaining(instr.getAddress())
        if func:
            fname = func.getName()
            faddr = func.getEntryPoint().getOffset()
            if faddr not in readers:
                readers.add(faddr)
                print("  %s @ %s [%s]" % (s, instr.getAddress(), fname))

# Decompile each reader to find the cap
print("\n[2] Decompiling readers looking for speed cap...")
for faddr in readers:
    func = listing.getFunctionAt(af.getAddress(faddr))
    if not func:
        continue
    results = decomp.decompileFunction(func, 30, getMonitor())
    if not results or not results.decompileCompleted():
        continue
    c = results.getDecompiledFunction().getC()
    # Look for comparisons, if-statements with 0x16 or speed-related logic
    if "0x47" in c and ("0x16" in c or "> " in c or "< " in c or "cmp" in c.lower()):
        lines = c.split("\n")
        print("\n  === %s ===" % func.getName())
        for i, line in enumerate(lines):
            if "0x47" in line or "0x16" in line or (">" in line and "0x" in line):
                for j in range(max(0,i-3), min(len(lines),i+4)):
                    m = ">>>" if j == i else "   "
                    print("    %s %s" % (m, lines[j]))
                print("    ---")

# Also look for the BLE status response builder that sends byte 26 (max speed)
print("\n[3] FUN_080101f4 - Status response builder (0x70):")
func = listing.getFunctionAt(af.getAddress(0x080101f4))
if func:
    results = decomp.decompileFunction(func, 30, getMonitor())
    if results and results.decompileCompleted():
        c = results.getDecompiledFunction().getC()
        lines = c.split("\n")
        for i, line in enumerate(lines):
            if "0x47" in line or "0x16" in line or "0x19" in line or "speed" in line.lower():
                for j in range(max(0,i-3), min(len(lines),i+4)):
                    m = ">>>" if j == i else "   "
                    print("    %s %s" % (m, lines[j]))
                print("    ---")

decomp.dispose()
print("\nDone.")
