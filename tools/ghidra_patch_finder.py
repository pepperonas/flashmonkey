# -*- coding: utf-8 -*-
# Find the exact patch point for speed limit in Navee firmware
# @category Navee
# @runtime Jython

program = currentProgram
listing = program.getListing()
memory = program.getMemory()
ref_mgr = program.getReferenceManager()
decomp = ghidra.app.decompiler.DecompInterface()
decomp.openProgram(program)

af = program.getAddressFactory().getDefaultAddressSpace()

print("=" * 60)
print("PATCH POINT FINDER")
print("=" * 60)

# 1. Find DAT_08012fb4 - pointer to sys_stc struct
print("\n[1] sys_stc struct pointer (DAT_08012fb4)...")
ptr_addr = af.getAddress(0x08012fb4)
try:
    ptr_val = memory.getInt(ptr_addr)
    print("  DAT_08012fb4 = 0x%08X (pointer to sys_stc)" % (ptr_val & 0xFFFFFFFF))
except:
    print("  Could not read pointer value")

# 2. Find ALL references to DAT_08012fb4 (sys_stc struct)
print("\n[2] All references to sys_stc pointer...")
refs = ref_mgr.getReferencesTo(ptr_addr)
funcs_using_sys_stc = set()
for ref in refs:
    func = listing.getFunctionContaining(ref.getFromAddress())
    if func:
        funcs_using_sys_stc.add(func.getEntryPoint().getOffset())
print("  %d functions reference sys_stc" % len(funcs_using_sys_stc))

# 3. Find the "lift_speed_limit" and "speed limit" strings and trace back
print("\n[3] Tracing lift_speed_limit string...")
# Search for the string bytes directly in memory
search_bytes = "lift_speed_limit"
addr = memory.findBytes(af.getAddress(0x08000000), search_bytes.encode('ascii'), None, True, getMonitor())
if addr:
    print("  Found '%s' at %s" % (search_bytes, addr))
    # Find what references this string address
    refs = ref_mgr.getReferencesTo(addr)
    for ref in refs:
        print("  Referenced from %s" % ref.getFromAddress())

# Search for "speed limit" more broadly
for search in ["speed_limit", "speed limit", "lift_speed"]:
    addr = memory.findBytes(af.getAddress(0x08000000), search.encode('ascii'), None, True, getMonitor())
    while addr:
        print("  '%s' found at %s" % (search, addr))
        # Get all references
        nearby_refs = ref_mgr.getReferencesTo(addr)
        for ref in nearby_refs:
            print("    <- ref from %s" % ref.getFromAddress())
        # Search for next occurrence
        try:
            addr = memory.findBytes(addr.add(1), search.encode('ascii'), None, True, getMonitor())
        except:
            break

# 4. Decompile functions that write to sys_stc+0x47 (max speed)
print("\n[4] Functions writing to sys_stc + 0x47 (max speed)...")
# Search for strb instructions with offset 0x47
instr_iter = listing.getInstructions(True)
found_writers = []
while instr_iter.hasNext() and not getMonitor().isCancelled():
    instr = instr_iter.next()
    s = str(instr)
    # Look for stores to offset 0x47 - strb rX,[rY,#0x47]
    if "#0x47" in s and ("strb" in s or "str" in s):
        func = listing.getFunctionContaining(instr.getAddress())
        fname = func.getName() if func else "?"
        print("  %s @ %s [%s]" % (s, instr.getAddress(), fname))
        if func and func.getEntryPoint().getOffset() not in [f[0] for f in found_writers]:
            found_writers.append((func.getEntryPoint().getOffset(), func))

# Decompile these functions
for _, func in found_writers[:5]:
    print("\n  === Decompiling %s ===" % func.getName())
    results = decomp.decompileFunction(func, 30, getMonitor())
    if results and results.decompileCompleted():
        c = results.getDecompiledFunction().getC()
        lines = c.split("\n")
        for i, line in enumerate(lines):
            if any(k in line for k in ["0x47", "speed", "limit", "max", "lift"]):
                for j in range(max(0,i-3), min(len(lines),i+4)):
                    m = ">>>" if j == i else "   "
                    print("  %s %s" % (m, lines[j]))
                print("  ---")

# 5. Search for where value 22 is assigned in context of speed
print("\n[5] Looking for CMP/MOV with speed-related values near sys_stc access...")
instr_iter = listing.getInstructions(True)
speed_instructions = []
while instr_iter.hasNext() and not getMonitor().isCancelled():
    instr = instr_iter.next()
    s = str(instr)
    addr_val = instr.getAddress().getOffset()
    # movs rX,#0x16 or cmp rX,#0x16
    if ("#0x16" in s and ("mov" in s or "cmp" in s)) and not "#0x16" in s.replace("#0x16","",1):
        func = listing.getFunctionContaining(instr.getAddress())
        if func and func.getEntryPoint().getOffset() in funcs_using_sys_stc:
            fname = func.getName()
            print("  MATCH: %s @ %s [%s] (uses sys_stc!)" % (s, instr.getAddress(), fname))
            speed_instructions.append((instr.getAddress(), func))

# Decompile matched functions
for addr, func in speed_instructions[:5]:
    print("\n  === %s (contains 0x16 + sys_stc) ===" % func.getName())
    results = decomp.decompileFunction(func, 30, getMonitor())
    if results and results.decompileCompleted():
        c = results.getDecompiledFunction().getC()
        # Print sections with 0x16 or 22
        lines = c.split("\n")
        for i, line in enumerate(lines):
            if "0x16" in line or "22" in line or "0x47" in line or "speed" in line.lower() or "limit" in line.lower():
                for j in range(max(0,i-2), min(len(lines),i+3)):
                    m = ">>>" if j == i else "   "
                    print("    %s %s" % (m, lines[j]))
                print("    ---")

# 6. Find the key long press handler (references "key long set save unit %d speed limit %d")
print("\n[6] Key long press speed limit handler...")
key_str_addr = af.getAddress(0x08013654)
refs = ref_mgr.getReferencesTo(key_str_addr)
for ref in refs:
    func = listing.getFunctionContaining(ref.getFromAddress())
    if func:
        print("  Function: %s @ %s" % (func.getName(), func.getEntryPoint()))
        results = decomp.decompileFunction(func, 30, getMonitor())
        if results and results.decompileCompleted():
            print(results.getDecompiledFunction().getC()[:4000])

# Also check indirect references - the string might be in a pointer table
print("\n[7] Searching for pointer to speed limit strings...")
for str_addr_int in [0x08013654, 0x08013694]:
    # Search for the 4-byte address in memory
    import struct
    addr_bytes = struct.pack("<I", str_addr_int)
    found = memory.findBytes(af.getAddress(0x08000000), addr_bytes, None, True, getMonitor())
    while found:
        print("  Pointer to 0x%08X found at %s" % (str_addr_int, found))
        refs2 = ref_mgr.getReferencesTo(found)
        for r in refs2:
            func = listing.getFunctionContaining(r.getFromAddress())
            if func:
                print("    <- %s [%s]" % (r.getFromAddress(), func.getName()))
        try:
            found = memory.findBytes(found.add(1), addr_bytes, None, True, getMonitor())
        except:
            break

decomp.dispose()
print("\nDone.")
