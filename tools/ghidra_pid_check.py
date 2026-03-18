# -*- coding: utf-8 -*-
# Find the PID check and speed limit assignment
# @category Navee
# @runtime Jython

program = currentProgram
listing = program.getListing()
memory = program.getMemory()
af = program.getAddressFactory().getDefaultAddressSpace()
decomp = ghidra.app.decompiler.DecompInterface()
decomp.openProgram(program)

print("=" * 60)
print("PID CHECK & SPEED LIMIT ASSIGNMENT")
print("=" * 60)

# FUN_08010d64 calls FUN_080109ae - decompile it
print("\n[1] FUN_08010d64 - CALLER of speed limit setter:")
func = listing.getFunctionAt(af.getAddress(0x08010d64))
if func:
    results = decomp.decompileFunction(func, 60, getMonitor())
    if results and results.decompileCompleted():
        c = results.getDecompiledFunction().getC()
        print(c[:6000])

# Also decompile FUN_0800e9d0 fully - the init function with default 0x1e (30)
print("\n\n[2] FUN_0800e9d0 - INIT with default 0x1e (30 km/h):")
func = listing.getFunctionAt(af.getAddress(0x0800e9d0))
if func:
    # Get the raw bytes for the instruction that sets 0x1e
    print("  Searching for movs rX,#0x1e instruction...")
    body = func.getBody()
    addr_iter = body.getAddresses(True)
    while addr_iter.hasNext():
        addr = addr_iter.next()
        instr = listing.getInstructionAt(addr)
        if instr and "#0x1e" in str(instr) and "mov" in str(instr).lower():
            raw = ""
            for i in range(instr.getLength()):
                raw += "%02x " % (memory.getByte(addr.add(i)) & 0xFF)
            print("  FOUND: %s: %s %s" % (addr, raw.strip(), instr))
            # Calculate file offset (base address is 0x08000000, file starts at 0x10)
            file_offset = addr.getOffset() - 0x08000000 + 0x10
            print("  FILE OFFSET: 0x%04X" % file_offset)
            print("  TO PATCH: change 0x1e (30) to desired speed")

# Search for the init function's strb with -0x3f offset near 0x1e
print("\n[3] All movs/mov instructions with #0x1e in the firmware:")
instr_iter = listing.getInstructions(True)
count = 0
while instr_iter.hasNext() and not getMonitor().isCancelled():
    instr = instr_iter.next()
    s = str(instr)
    if "#0x1e" in s and ("mov" in s.lower()):
        func = listing.getFunctionContaining(instr.getAddress())
        fname = func.getName() if func else "?"
        file_offset = instr.getAddress().getOffset() - 0x08000000 + 0x10
        raw = ""
        for i in range(instr.getLength()):
            raw += "%02x " % (memory.getByte(instr.getAddress().add(i)) & 0xFF)
        print("  %s: %s %s [%s] FILE:0x%04X" % (instr.getAddress(), raw.strip(), s, fname, file_offset))
        count += 1
print("  Total: %d" % count)

# Also look for comparisons with 22 (0x16) that might cap the speed
print("\n[4] CMP instructions with #0x16 in speed-related functions:")
for func_addr in [0x080109ae, 0x08010d64, 0x0800e9d0, 0x0800eac2]:
    func = listing.getFunctionAt(af.getAddress(func_addr))
    if not func:
        continue
    body = func.getBody()
    addr_iter = body.getAddresses(True)
    while addr_iter.hasNext():
        addr = addr_iter.next()
        instr = listing.getInstructionAt(addr)
        if instr and "cmp" in str(instr).lower() and "#0x16" in str(instr):
            file_offset = addr.getOffset() - 0x08000000 + 0x10
            print("  %s: %s [%s] FILE:0x%04X" % (addr, instr, func.getName(), file_offset))

decomp.dispose()
print("\nDone.")
