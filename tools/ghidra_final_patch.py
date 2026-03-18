# -*- coding: utf-8 -*-
# Final analysis: decompile the speed limit setter and find patch point
# @category Navee
# @runtime Jython

program = currentProgram
listing = program.getListing()
memory = program.getMemory()
af = program.getAddressFactory().getDefaultAddressSpace()
decomp = ghidra.app.decompiler.DecompInterface()
decomp.openProgram(program)

print("=" * 60)
print("FINAL PATCH ANALYSIS")
print("=" * 60)

# 1. Full decompile of FUN_080109ae (speed limit setter)
print("\n[1] FUN_080109ae - SPEED LIMIT SETTER (full decompile):")
func = listing.getFunctionAt(af.getAddress(0x080109ae))
if func:
    results = decomp.decompileFunction(func, 30, getMonitor())
    if results and results.decompileCompleted():
        print(results.getDecompiledFunction().getC())

# 2. Full decompile of FUN_0800e9d0 (also writes to +0x47)
print("\n[2] FUN_0800e9d0 - ANOTHER WRITER (full decompile):")
func = listing.getFunctionAt(af.getAddress(0x0800e9d0))
if func:
    results = decomp.decompileFunction(func, 30, getMonitor())
    if results and results.decompileCompleted():
        print(results.getDecompiledFunction().getC()[:3000])

# 3. Full decompile of FUN_0800eac2 (also writes to +0x47)
print("\n[3] FUN_0800eac2 - INIT/CONFIG WRITER (full decompile):")
func = listing.getFunctionAt(af.getAddress(0x0800eac2))
if func:
    results = decomp.decompileFunction(func, 30, getMonitor())
    if results and results.decompileCompleted():
        c = results.getDecompiledFunction().getC()
        # Print sections near 0x47 writes
        lines = c.split("\n")
        for i, line in enumerate(lines):
            if "0x47" in line or "0x16" in line or "speed" in line.lower() or "limit" in line.lower() or "max" in line.lower():
                for j in range(max(0,i-5), min(len(lines),i+6)):
                    m = ">>>" if j == i else "   "
                    print("  %s %s" % (m, lines[j]))
                print("  ---")

# 4. Disassemble FUN_080109ae instruction by instruction
print("\n[4] FUN_080109ae DISASSEMBLY:")
func = listing.getFunctionAt(af.getAddress(0x080109ae))
if func:
    body = func.getBody()
    addr_set = body.getAddresses(True)
    while addr_set.hasNext():
        addr = addr_set.next()
        instr = listing.getInstructionAt(addr)
        if instr:
            raw = ""
            for i in range(instr.getLength()):
                raw += "%02x " % (memory.getByte(addr.add(i)) & 0xFF)
            print("  %s: %-12s %s" % (addr, raw.strip(), instr))

# 5. What calls FUN_080109ae?
print("\n[5] Callers of FUN_080109ae:")
refs = program.getReferenceManager().getReferencesTo(af.getAddress(0x080109ae))
for ref in refs:
    caller_func = listing.getFunctionContaining(ref.getFromAddress())
    if caller_func:
        print("  Called from %s in %s" % (ref.getFromAddress(), caller_func.getName()))

# 6. What is DAT_08010b00? (pointer to sys_stc)
print("\n[6] DAT_08010b00 value:")
try:
    val = memory.getInt(af.getAddress(0x08010b00))
    print("  DAT_08010b00 = 0x%08X" % (val & 0xFFFFFFFF))
except:
    print("  Could not read")

# 7. Look at DAT_08010af0 and DAT_08010af4
print("\n[7] Related data pointers:")
for dat_addr in [0x08010af0, 0x08010af4, 0x08010b00]:
    try:
        val = memory.getInt(af.getAddress(dat_addr))
        print("  DAT_%08X = 0x%08X" % (dat_addr, val & 0xFFFFFFFF))
    except:
        pass

decomp.dispose()
print("\nDone.")
