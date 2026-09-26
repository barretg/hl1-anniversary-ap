"""Convert halflife-op4-updated sources to the HL25 SDK's conventions.

    python tools/port_of.py <file relative to op4 dlls/> ...
    python tools/port_of.py --anims    # regenerate of_weapon_anims.h

Writes game/src/port/of/<basename>. Mechanical only: return types of base
virtuals, KeyValue's void form, the license header, include names. Hand
fixes after conversion are listed in game/src/port/of/README.md.

OF_SDK (default ../halflife-op4-updated) and HLSDK_DIR (default ../halflife)
point at the two checkouts.
"""
import os
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
OF = pathlib.Path(os.environ.get("OF_SDK", ROOT.parent / "halflife-op4-updated")) / "dlls"
HL25 = pathlib.Path(os.environ.get("HLSDK_DIR", ROOT.parent / "halflife")) / "dlls"
OUT = ROOT / "game/src/port/of"
HEADER = ((ROOT / "game/src/port/bs_rosenberg.cpp")
          .read_text().split("****/", 1)[0] + "****/\n")


def virtual_types(d):
    out = {}
    for h in ["cbase.h", "basemonster.h", "talkmonster.h", "squadmonster.h",
              "monsters.h", "weapons.h", "player.h", "effects.h", "items.h"]:
        p = d / h
        if not p.exists():
            continue
        for line in p.read_text(errors="ignore").splitlines():
            if "virtual" not in line:
                continue
            m = re.match(r"\s*virtual\s+([\w\*\s:&<>]+?)\s*\b(\w+)\s*\(", line)
            if m:
                out[m.group(2)] = re.sub(r"\s+", "", m.group(1))
    return out


def split_params(text):
    text = text.strip()
    if not text or text == "void":
        return []
    return [x.strip() for x in text.split(",")]


def param_type(param):
    param = param.split("=")[0].strip()
    m = re.match(r"(.*?[\w\*&\s])\s*\b(\w+)\s*$", param)
    # "const char *name" -> "const char *"; a lone type keeps itself.
    if m and re.search(r"\w", m.group(1)) and m.group(1).strip() not in ("const", "unsigned"):
        return m.group(1).strip()
    return param


def virtual_params(d):
    out = {}
    for h in ["cbase.h", "basemonster.h", "talkmonster.h", "squadmonster.h",
              "monsters.h", "weapons.h", "player.h", "effects.h", "items.h"]:
        p = d / h
        if not p.exists():
            continue
        for m in re.finditer(r"virtual\s+[\w\*\s:&<>]+?\b(\w+)\s*\(([^)]*)\)", p.read_text(errors="ignore")):
            params = split_params(m.group(2))
            out[(m.group(1), len(params))] = [param_type(x) for x in params]
    return out


OF_T, HL_T = virtual_types(OF), virtual_types(HL25)
HL_P = virtual_params(HL25)
RENAME = {"PlaySentenceCore": "PlaySentence"}
# One declared parameter: "const char* name", "Task_t *pTask", "bool b = false".
DECL = re.compile(r"^(?:const\s+)?(?:unsigned\s+)?[A-Za-z_][\w:]*(?:\s*[\*&]+\s*|\s+)(?:const\s*)?\w+(?:\s*=.*)?$")


def same(a, b):
    """True if two parameter types differ only in bool/BOOL/int or const."""
    norm = lambda t: re.sub(r"\b(?:bool|BOOL|int)\b", "B", re.sub(r"\bconst\b|\s", "", t))
    return norm(a) == norm(b) or False


def fix_params(text):
    """Give overrides and their definitions this SDK's parameter types."""
    def repl(m):
        name, params = m.group(1), split_params(m.group(2))
        want = HL_P.get((name.split("::")[-1], len(params)))
        if not want or not params or not all(DECL.match(x) for x in params):
            return m.group(0)  # a call, or nothing to match
        if any(same(param_type(h), t) is False for h, t in zip(params, want)):
            return m.group(0)  # another class's method of the same name
        fixed = []
        for have, typ in zip(params, want):
            default = ""
            if "=" in have:
                have, default = have.split("=", 1)
                default = " =" + default
            n = re.search(r"(\w+)\s*$", have.strip())
            fixed.append(f"{typ} {n.group(1)}{default}" if n and param_type(have) != have.strip() else typ + default)
        return f"{name}({', '.join(fixed)})"
    return re.sub(r"\b((?:\w+::)?\w+)\(([^()]*)\)(?=\s*(?:const\s*)?(?:override|\{|\n\s*\{|;))", repl, text)
RETYPE = {n: HL_T[n] for n in OF_T if n in HL_T and OF_T[n] != HL_T[n]
          and OF_T[n] == "bool" and n != "KeyValue"}


def bodies(text, name):
    """(start, end) of each function body `...name(KeyValueData...) ... { }`."""
    for m in re.finditer(r"\b" + name + r"\s*\(\s*KeyValueData\s*\*\s*\w+\s*\)[^;{]*\{", text):
        i, depth = m.end(), 1
        while depth:
            depth += {"{": 1, "}": -1}.get(text[i], 0)
            i += 1
        yield m.end(), i - 1


def drop_ctf(text):
    """Capture the flag is multiplayer: drop its includes and its blocks."""
    text = re.sub(r'#include\s+"(?:ctf/)?(?:CTF|ctf)\w*\.h"\n', "", text)
    # halflife-updated gathers the gmsg* ids here; this SDK declares them where used.
    text = text.replace('#include "UserMessages.h"\n', "")
    while True:
        m = re.search(r"\n([ \t]*)if \((?:g_pGameRules->IsCTF\(\)|\(m_pPlayer->m_iItems & CTFItem::)[^\n]*\n\1\{", text)
        if not m:
            return text
        i, depth = m.end(), 1
        while depth:
            depth += {"{": 1, "}": -1}.get(text[i], 0)
            i += 1
        assert not re.match(r"\s*else", text[i:]), "CTF block with an else"
        text = text[:m.start()] + text[i:]


def convert(text):
    text = drop_ctf(text)
    text = re.sub(r"\A/\*\*\*.*?\*\*\*\*/\n", HEADER, text, flags=re.S)
    for name, typ in RETYPE.items():
        text = re.sub(r"\bbool(\s+(?:\w+::)?" + name + r"\s*\()", typ + r"\1", text)
    for a, b in RENAME.items():
        text = re.sub(r"\b" + a + r"\b", b, text)
    text = fix_params(text)
    # KeyValue returns void here and reports through fHandled.
    out, last = [], 0
    for a, b in bodies(text, "KeyValue"):
        body = text[a:b]
        body = re.sub(r"return\s+(\w+::KeyValue\s*\(\s*\w+\s*\))\s*;", r"{ \1; return; }", body)
        body = re.sub(r"return\s+true\s*;", "{ pkvd->fHandled = TRUE; return; }", body)
        body = re.sub(r"return\s+false\s*;", "return;", body)
        out += [text[last:a], body]
        last = b
    text = "".join(out + [text[last:]])
    text = re.sub(r"\bbool(\s+(?:\w+::)?KeyValue\s*\()", r"void\1", text)
    # Helpers this SDK lacks.
    last = list(re.finditer(r'^#include[^\n]*\n', text, flags=re.M))
    if last and "port_compat.h" not in text:
        i = last[-1].end()
        text = text[:i] + '#include "port_compat.h"\n' + text[i:]
    # Holster takes skiplocal here.
    text = re.sub(r"\bvoid Holster\(\) override;", "void Holster(int skiplocal = 0) override;", text)
    text = re.sub(r"\bvoid (\w+)::Holster\(\)", r"void \1::Holster(int skiplocal)", text)
    # GET_PRIVATE is a plain macro here; the world is entity 0.
    text = re.sub(r"\bGET_PRIVATE<(\w+)>\(((?:[^()]|\([^()]*\))*)\)", r"((\1*)GET_PRIVATE(\2))", text)
    text = re.sub(r"\bm_SndRoomtype\b", "m_flSndRoomtype", text)
    text = text.replace("EntSelectSpawnPoint(CBasePlayer* pPlayer)", "EntSelectSpawnPoint(CBaseEntity* pPlayer)")
    # PLAYBACK_EVENT_FULL takes float *: `(float *)&g_vecZero` as Valve writes it.
    text = re.sub(r"PLAYBACK_EVENT_FULL\((?:[^()]|\([^()]*\))*\)",
                  lambda m: re.sub(r"(?<![&\w])g_vecZero\b", "(float*)&g_vecZero", m.group(0)), text)
    text = text.replace("CWorld::World->edict()", "INDEXENT(0)")
    # sv_oldgrapple is fixed at 0 (of_cvars.cpp), so the client needs no cvar
    # lookup, nor cl_dll.h, whose Vector clashes with the server's.
    text = text.replace('#else\n#include "cl_dll.h"\n#endif\n', "#endif\n")
    text = text.replace('gEngfuncs.pfnGetCvarFloat("sv_oldgrapple")', "0.0f")
    # Flattened: rope/ and weapons/ live beside everything else.
    text = re.sub(r'#include\s+"(?:rope|weapons|ctf)/(\w+\.h)"', r'#include "\1"', text)
    return text


# The weapons whose events the client plays, and what those events need.
ANIM_HEADERS = ["CEagle", "CPipewrench", "CM249", "CDisplacer", "CShockRifle",
                "CSporeLauncher", "CSniperRifle", "CKnife"]


def write_anims():
    """of_weapon_anims.h: the enums and constants the client's events use, from
    the ported headers, which ev_hldm.cpp cannot include."""
    out = ["// Generated by tools/port_of.py --anims from the ported weapon headers:",
           "// what the client's events need, without the server headers ev_hldm.cpp",
           "// cannot include.", "#pragma once", "",
           "#ifndef WEAPON_M249", "#define WEAPON_M249 19 // as in dlls/weapons.h", "#endif", ""]
    for name in ANIM_HEADERS:
        text = (OUT / f"{name}.h").read_text()
        for m in re.finditer(r"^enum[^\n]*\n\{.*?^\};\n|^static const [^\n]*;\n", text, flags=re.S | re.M):
            out.append(m.group(0))
    (OUT / "of_weapon_anims.h").write_text("\n".join(out))


def main(argv):
    OUT.mkdir(parents=True, exist_ok=True)
    if argv == ["--anims"]:
        write_anims()
        return
    for rel in argv:
        src = OF / rel
        dst = OUT / src.name
        dst.write_text(convert(src.read_text(errors="ignore")))
        print(dst)


if __name__ == "__main__":
    main(sys.argv[1:])
