"""Vtable layouts for HL:S's server.dll, read from the binaries themselves.

HL:S ships no game source and its Windows server.dll has no symbols. It does
carry MSVC RTTI, so every polymorphic class's vftable can be found by name.
The macOS server.dylib shipped beside it is the same code with a full symbol
table, so its Itanium vtables name every slot. This tool reads both, converts
the Itanium order to MSVC's, and refuses to emit anything unless the converted
length matches the dll's vftable exactly.

Itanium to MSVC, per class that introduces virtuals:
- a virtual destructor takes two Itanium slots (complete, deleting) and one in
  MSVC (scalar deleting);
- MSVC groups overloads of one name at the first one's position, in reverse
  declaration order. Itanium keeps declaration order.

Standard library only, so it runs anywhere the repo does.

    python hl-source/tools/source_rtti.py --hls "<Half-Life 2>" \
        --class CHL1_Player --class CHalfLife1 [--header out.h] [--dump]
"""

from __future__ import annotations

import argparse
import struct
import subprocess
import sys
from pathlib import Path


# -- Mach-O (32-bit, i386) -------------------------------------------------

class MachO:
    def __init__(self, data: bytes):
        self.data = data
        magic, _cpu, _sub, _ft, ncmds, _size, _flags = struct.unpack_from("<7I", data, 0)
        if magic != 0xFEEDFACE:
            raise ValueError("not a 32-bit little-endian Mach-O")
        self.segments = []  # (vmaddr, vmsize, fileoff, filesize)
        self.sections = []  # (addr, size, offset, segname, sectname)
        symoff = nsyms = stroff = 0
        off = 28
        for _ in range(ncmds):
            cmd, cmdsize = struct.unpack_from("<2I", data, off)
            if cmd == 1:  # LC_SEGMENT
                seg = data[off + 8:off + 24].rstrip(b"\0").decode()
                vmaddr, vmsize, fileoff, filesize, _mp, _ip, nsects, _f = \
                    struct.unpack_from("<8I", data, off + 24)
                self.segments.append((vmaddr, vmsize, fileoff, filesize))
                s = off + 56
                for _ in range(nsects):
                    sect = data[s:s + 16].rstrip(b"\0").decode()
                    addr, size, offset = struct.unpack_from("<3I", data, s + 32)
                    self.sections.append((addr, size, offset, seg, sect))
                    s += 68
            elif cmd == 2:  # LC_SYMTAB
                symoff, nsyms, stroff, _ = struct.unpack_from("<4I", data, off + 8)
            off += cmdsize
        self.by_name: dict[str, int] = {}
        self.by_addr: dict[int, str] = {}
        for i in range(nsyms):
            strx, ntype, nsect, _desc, value = struct.unpack_from("<IBBhI", data, symoff + 12 * i)
            if ntype & 0xE0 or (ntype & 0x0E) != 0x0E:  # stabs, or not defined in a section
                continue
            end = data.index(b"\0", stroff + strx)
            name = data[stroff + strx:end].decode()
            self.by_name.setdefault(name, value)
            # Prefer the first name seen for an address; identical-code folding
            # can alias several, and any of them identifies the slot.
            self.by_addr.setdefault(value, name)
        self.text = [(a, a + n) for a, n, _o, seg, _s in self.sections if seg == "__TEXT"]

    def u32(self, addr: int) -> int:
        for vmaddr, vmsize, fileoff, filesize in self.segments:
            if vmaddr <= addr < vmaddr + min(vmsize, filesize):
                return struct.unpack_from("<I", self.data, fileoff + addr - vmaddr)[0]
        raise KeyError(hex(addr))

    def is_code(self, addr: int) -> bool:
        return any(a <= addr < b for a, b in self.text)

    def vtable(self, cls: str) -> list[str]:
        """Primary vtable slots of `cls`, mangled names, '' for a pure virtual."""
        sym = f"__ZTV{len(cls)}{cls}"
        if sym not in self.by_name:
            raise KeyError(f"no vtable symbol {sym} in the dylib")
        addr = self.by_name[sym] + 8  # skip offset-to-top and typeinfo
        slots = []
        while True:
            v = self.u32(addr)
            if v == 0:
                slots.append("")  # __cxa_pure_virtual, bound at load time
            elif self.is_code(v) and v in self.by_addr:
                slots.append(self.by_addr[v])
            else:
                break
            addr += 4
        # Trailing zeros are the next group's offset-to-top, not pure virtuals.
        while slots and slots[-1] == "":
            slots.pop()
        return slots


# -- PE (32-bit) -----------------------------------------------------------

class PE:
    def __init__(self, data: bytes):
        self.data = data
        e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
        if data[e_lfanew:e_lfanew + 4] != b"PE\0\0":
            raise ValueError("not a PE file")
        nsec = struct.unpack_from("<H", data, e_lfanew + 6)[0]
        optsize = struct.unpack_from("<H", data, e_lfanew + 20)[0]
        opt = e_lfanew + 24
        if struct.unpack_from("<H", data, opt)[0] != 0x10B:
            raise ValueError("not PE32")
        self.base = struct.unpack_from("<I", data, opt + 28)[0]
        self.sections = []  # (name, va, vsize, raw, rawsize, characteristics)
        s = opt + optsize
        for _ in range(nsec):
            name = data[s:s + 8].rstrip(b"\0").decode()
            vsize, va, rawsize, raw = struct.unpack_from("<4I", data, s + 8)
            chars = struct.unpack_from("<I", data, s + 36)[0]
            self.sections.append((name, self.base + va, vsize, raw, rawsize, chars))
            s += 40

    def off(self, va: int) -> int:
        for _n, sva, vsize, raw, rawsize, _c in self.sections:
            if sva <= va < sva + min(vsize, rawsize):
                return raw + va - sva
        raise KeyError(hex(va))

    def va(self, off: int) -> int:
        for _n, sva, _vs, raw, rawsize, _c in self.sections:
            if raw <= off < raw + rawsize:
                return sva + off - raw
        raise KeyError(off)

    def is_code(self, va: int) -> bool:
        return any(sva <= va < sva + vs and c & 0x20000000
                   for _n, sva, vs, _r, _rs, c in self.sections)

    def u32(self, va: int) -> int:
        return struct.unpack_from("<I", self.data, self.off(va))[0]

    def _dwords_equal(self, value: int) -> list[int]:
        needle = struct.pack("<I", value)
        out, i = [], self.data.find(needle)
        while i != -1:
            if i % 4 == 0:
                try:
                    out.append(self.va(i))
                except KeyError:
                    pass
            i = self.data.find(needle, i + 1)
        return out

    def vftable(self, cls: str) -> tuple[int, int]:
        """(address, slot count) of `cls`'s primary vftable, via RTTI."""
        name = f".?AV{cls}@@".encode() + b"\0"
        i = self.data.find(name)
        if i < 0:
            raise KeyError(f"no RTTI type descriptor for {cls} in the dll")
        td = self.va(i) - 8
        for ref in self._dwords_equal(td):
            col = ref - 12  # CompleteObjectLocator.pTypeDescriptor is at +12
            try:
                sig, offset = struct.unpack_from("<2I", self.data, self.off(col))
            except KeyError:
                continue
            if sig != 0 or offset != 0:
                continue  # a secondary base's locator
            for meta in self._dwords_equal(col):
                vft = meta + 4
                n = 0
                while self.is_code(self.u32(vft + 4 * n)):
                    n += 1
                if n:
                    return vft, n
        raise KeyError(f"no primary vftable for {cls}")


# -- Itanium to MSVC -------------------------------------------------------

def demangle(names: list[str]) -> list[str]:
    if not names:
        return []
    out = subprocess.run(["c++filt", "-_"], input="\n".join(names), text=True,
                         capture_output=True, check=True).stdout.splitlines()
    return out


def method_name(demangled: str) -> str:
    """`CBasePlayer::BumpWeapon(CBaseCombatWeapon*)` -> `BumpWeapon`."""
    head = demangled.split("(", 1)[0]
    return head.rsplit("::", 1)[-1]


def to_msvc(dylib: MachO, cls: str) -> list[tuple[str, str]]:
    """MSVC-ordered (method name, demangled Itanium name) for `cls`."""
    chain = []  # primary-base chain, base first
    c = cls
    while c:
        # Abstract interfaces have no vtable symbol; their slots are counted
        # with the first base that has one. None of them overload a name that
        # CBaseEntity or CGameRules also declares, so the grouping is the same.
        if f"__ZTV{len(c)}{c}" in dylib.by_name:
            chain.insert(0, c)
        c = primary_base(dylib, c)
    prev_len = 0
    msvc: list[tuple[str, str]] = []
    full = dylib.vtable(cls)
    full_d = demangle([n for n in full if n])
    it = iter(full_d)
    full_named = [(method_name(d), d) for d in (next(it) if n else "" for n in full)]
    for c in chain:
        n = len(dylib.vtable(c))
        new = full_named[prev_len:n]
        prev_len = n
        # Destructors: two Itanium slots, one MSVC slot.
        merged, skip = [], False
        for i, slot in enumerate(new):
            if skip:
                skip = False
                continue
            if slot[0].startswith("~") and i + 1 < len(new) and new[i + 1][0] == slot[0]:
                skip = True
            merged.append(slot)
        # Overloads: grouped at the first one's position, reversed.
        order: list[str] = []
        groups: dict[str, list[tuple[str, str]]] = {}
        for slot in merged:
            key = slot[0] or f"<pure{len(order)}>"
            if key not in groups:
                order.append(key)
                groups[key] = []
            groups[key].append(slot)
        for key in order:
            msvc.extend(reversed(groups[key]))
    return msvc


def primary_base(dylib: MachO, cls: str) -> str | None:
    """Primary base from the Itanium typeinfo (__ZTI)."""
    sym = f"__ZTI{len(cls)}{cls}"
    if sym not in dylib.by_name:
        return None
    ti = dylib.by_name[sym]
    # The typeinfo's own vptr is an import bound at load time, so it reads as
    # zero here. Tell the kinds apart by shape instead: a single-inheritance
    # typeinfo's third word is its base's typeinfo; a multiple-inheritance
    # one's is a flags word followed by a base count.
    def is_ti(addr: int) -> bool:
        return dylib.by_addr.get(addr, "").startswith("__ZTI")
    if is_ti(dylib.u32(ti + 8)):
        base_ti = dylib.u32(ti + 8)
    elif 0 < dylib.u32(ti + 12) < 16 and is_ti(dylib.u32(ti + 16)):
        nbases = dylib.u32(ti + 12)
        base_ti = 0
        for b in range(nbases):
            bti, flags = dylib.u32(ti + 16 + 8 * b), dylib.u32(ti + 20 + 8 * b)
            if flags >> 8 == 0 and flags & 2:  # public, at offset 0
                base_ti = bti
                break
        if not base_ti:
            return None
    else:
        return None
    name = dylib.by_addr.get(base_ti, "")
    if not name.startswith("__ZTI"):
        return None
    mangled = name[5:]
    i = 0
    while mangled[i].isdigit():
        i += 1
    return mangled[i:i + int(mangled[:i])]


# -- Driver ----------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--hls", required=True, type=Path, help="the Half-Life 2 install folder")
    ap.add_argument("--class", dest="classes", action="append", required=True)
    ap.add_argument("--header", type=Path, help="write slot constants here")
    ap.add_argument("--dump", action="store_true", help="print every slot")
    args = ap.parse_args()

    bindir = args.hls / "hl1" / "bin"
    dylib = MachO((bindir / "server.dylib").read_bytes())
    pe = PE((bindir / "server.dll").read_bytes())

    lines = ["// Generated by hl-source/tools/source_rtti.py. Do not edit.",
             "// MSVC vtable slot indices in HL:S's server.dll.", "#pragma once", ""]
    ok = True
    # A second check beyond length: a function the dylib places in several
    # classes' vtables must sit at one address in the dll too. A wrong overload
    # order or a misplaced class boundary breaks that at once.
    seen_at: dict[str, int] = {}
    for cls in args.classes:
        slots = to_msvc(dylib, cls)
        vft, n = pe.vftable(cls)
        match = len(slots) == n
        for i, (_m, d) in enumerate(slots if match else []):
            addr = pe.u32(vft + 4 * i)
            if d and seen_at.setdefault(d, addr) != addr:
                print(f"{cls} slot {i}: {d} disagrees with another class", file=sys.stderr)
                match = False
        ok &= match
        print(f"{cls}: dll vftable 0x{vft:08x}, {n} slots; dylib converted {len(slots)}"
              f" -> {'ok' if match else 'MISMATCH'}")
        if args.dump:
            for i, (_m, d) in enumerate(slots):
                print(f"  {i:4d}  {d}")
        lines.append(f"// {cls}: {n} slots")
        seen: dict[str, int] = {}
        for i, (m, d) in enumerate(slots):
            if not m or m.startswith("~") or "<" in m or "operator" in m:
                continue
            seen[m] = seen.get(m, 0) + 1
            suffix = "" if seen[m] == 1 else f"_{seen[m]}"
            lines.append(f"constexpr int kSlot_{cls}_{m}{suffix} = {i};  // {d}")
        lines.append("")
    if not ok:
        print("refusing to write a header: layouts disagree", file=sys.stderr)
        return 1
    if args.header:
        args.header.parent.mkdir(parents=True, exist_ok=True)
        args.header.write_text("\n".join(lines))
        print(f"wrote {args.header}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
