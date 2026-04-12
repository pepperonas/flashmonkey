#!/usr/bin/env python3
"""Deep binary comparison: DE vs Global BLDC firmware.

Goes beyond the known 0xCF/0xB7 region byte — finds all structural
differences, speed/PWM tables, string differences, and code regions."""
import sys
from pathlib import Path

DE = Path("tools/firmware/navee_bldc_v0.0.1.5_ST3_PRO_DE_22km_h,_pid=23452.bin")
GL = Path("tools/firmware/navee_bldc_v0.0.1.1_ST3_Global,_pid=24012.bin")

de = DE.read_bytes()
gl = GL.read_bytes()

print(f"DE:     {len(de):>6} bytes  {DE.name}")
print(f"Global: {len(gl):>6} bytes  {GL.name}")
print(f"Diff:   {len(de)-len(gl):>+6} bytes\n")

# ---------- Header / metadata ----------
print("="*70)
print("HEADER COMPARISON (bytes 0-32)")
print("="*70)
for i in range(32):
    d, g = de[i], gl[i]
    if d != g:
        print(f"  [0x{i:04X}] DE={d:02X}  GL={g:02X}  diff")
    elif i < 20:
        # show first 20 for context
        pass

# ---------- Find all byte diffs in header/config area ----------
print("\n" + "="*70)
print("ALL DIFFS IN FIRST 512 BYTES (header + config)")
print("="*70)
for i in range(min(512, len(de), len(gl))):
    if de[i] != gl[i]:
        print(f"  [0x{i:04X}]  DE={de[i]:02X}  GL={gl[i]:02X}  ({de[i]-gl[i]:+d})")

# ---------- Strings ----------
def extract_strings(data, min_len=5):
    out, cur = [], bytearray()
    for i, b in enumerate(data):
        if 0x20 <= b <= 0x7E:
            cur.append(b)
        else:
            if len(cur) >= min_len:
                out.append((i - len(cur), cur.decode("ascii", errors="replace")))
            cur = bytearray()
    if len(cur) >= min_len:
        out.append((len(data) - len(cur), cur.decode("ascii", errors="replace")))
    return out

de_strings = dict(extract_strings(de))
gl_strings = dict(extract_strings(gl))
de_str_set = set(de_strings.values())
gl_str_set = set(gl_strings.values())

only_de = de_str_set - gl_str_set
only_gl = gl_str_set - de_str_set

print("\n" + "="*70)
print("STRINGS ONLY IN DE FIRMWARE")
print("="*70)
for s in sorted(only_de):
    offset = [o for o, v in de_strings.items() if v == s][0]
    print(f"  [0x{offset:04X}]  {s!r}")

print("\n" + "="*70)
print("STRINGS ONLY IN GLOBAL FIRMWARE")
print("="*70)
for s in sorted(only_gl):
    offset = [o for o, v in gl_strings.items() if v == s][0]
    print(f"  [0x{offset:04X}]  {s!r}")

# ---------- Find country code table ----------
print("\n" + "="*70)
print("COUNTRY CODE TABLE SEARCH")
print("="*70)
for needle in [b"CNESDE", b"CNES", b"EU", b"DE", b"Global"]:
    pos = de.find(needle)
    if pos != -1:
        print(f"  DE [0x{pos:04X}]  {de[pos:pos+40]!r}")
    pos = gl.find(needle)
    if pos != -1:
        print(f"  GL [0x{pos:04X}]  {gl[pos:pos+40]!r}")

# ---------- Speed/PWM tables: look for repeating patterns of small ints ----------
print("\n" + "="*70)
print("POTENTIAL SPEED/PWM TABLES (sequences of 4+ bytes in 15-80 range)")
print("="*70)
def find_number_tables(data, name):
    tables = []
    i = 0
    while i < len(data) - 4:
        # look for run of bytes in 15..80 (likely speed/PWM values)
        run_start = i
        while i < len(data) and 15 <= data[i] <= 80:
            i += 1
        if i - run_start >= 6:
            values = list(data[run_start:i])
            # heuristic: monotonic increase or plausible pwm scale
            if all(values[j] <= values[j+1] + 2 for j in range(len(values)-1)) and max(values) - min(values) > 5:
                tables.append((run_start, values))
        i += 1
    return tables

de_tables = find_number_tables(de, "DE")
gl_tables = find_number_tables(gl, "Global")

print(f"  DE tables found: {len(de_tables)}")
for off, vals in de_tables[:10]:
    print(f"    [0x{off:04X}]  {vals}")
print(f"\n  Global tables found: {len(gl_tables)}")
for off, vals in gl_tables[:10]:
    print(f"    [0x{off:04X}]  {vals}")

# ---------- ARM Cortex-M vector table ----------
print("\n" + "="*70)
print("ARM CORTEX-M VECTOR TABLE CHECK")
print("="*70)
import struct
for name, data in [("DE", de), ("Global", gl)]:
    # vector table typically at start of app (after header at 0x100)
    for base in [0x0, 0x100, 0x200, 0x1000]:
        if base + 8 > len(data):
            continue
        sp, reset = struct.unpack("<II", data[base:base+8])
        # heuristic: SP in RAM range (0x20000000-0x20008000 for LKS32), Reset in flash (<0x20000)
        if 0x20000000 <= sp <= 0x20010000 and reset < 0x100000:
            print(f"  {name:6}  vector_base=0x{base:04X}  SP=0x{sp:08X}  Reset=0x{reset:08X}")

# ---------- Large block diff summary ----------
print("\n" + "="*70)
print("BYTE-DIFF HEATMAP (per 1KB block)")
print("="*70)
common = min(len(de), len(gl))
block = 1024
print(f"  Block      DE-only diffs  (%)")
for b in range(0, common, block):
    blk_de = de[b:b+block]
    blk_gl = gl[b:b+block]
    diffs = sum(1 for a, c in zip(blk_de, blk_gl) if a != c)
    pct = 100 * diffs / len(blk_de) if blk_de else 0
    bar = "#" * int(pct / 5)
    print(f"  0x{b:04X}      {diffs:>4}/{len(blk_de):<4}  {pct:5.1f}%  {bar}")
