"""Convert the lobby whiteboard art into the TGAs client.dll reads.

`assets/-<n>whiteboard.png` becomes `mod/files/gfx/whiteboards/wb<nn>.tga`,
uncompressed 24-bit, which the client can parse without an image library. One
is picked at random each time the lobby loads; see
game/src/client/ap_whiteboard.h. The numbering has to stay contiguous from 0:
the client stops counting at the first gap.

Usage:
    python tools/build_whiteboards.py
"""

from __future__ import annotations

import re
import struct
import sys
from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent
ASSETS = REPO_ROOT / "assets"
OUT_DIR = REPO_ROOT / "apworld" / "half_life" / "mod" / "files" / "gfx" / "whiteboards"
PATTERN = re.compile(r"^-(\d+)whiteboard\.png$")


def write_tga(image: Image.Image, path: Path) -> None:
    rgb = image.convert("RGB")
    width, height = rgb.size
    # Type 2, 24 bpp, top-left origin.
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, width, height, 24, 0x20)
    r, g, b = rgb.split()
    path.write_bytes(header + Image.merge("RGB", (b, g, r)).tobytes())


def main() -> int:
    sources = {}
    for path in ASSETS.iterdir():
        match = PATTERN.match(path.name)
        if match:
            sources[int(match.group(1))] = path
    if not sources:
        print(f"no whiteboards in {ASSETS}", file=sys.stderr)
        return 1
    if sorted(sources) != list(range(len(sources))):
        print(f"whiteboard numbering has gaps: {sorted(sources)}", file=sys.stderr)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for old in OUT_DIR.glob("wb*.tga"):
        old.unlink()
    for index, path in sorted(sources.items()):
        write_tga(Image.open(path), OUT_DIR / f"wb{index:02d}.tga")
    print(f"wrote {len(sources)} whiteboards to {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
