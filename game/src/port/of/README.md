# Opposing Force port

Entities from Sam Vanheer's `halflife-op4-updated`, converted to this SDK's
conventions by `tools/port_of.py`. Every file here except the four below is
the script's output unchanged; fix the script rather than the file, then
re-run it on that file.

- `port_compat.h`: helpers the Updated SDK has and this one lacks.
- `of_skill.cpp`: OF's skill cvars, generated from its `skill.h`/`game.cpp`.
  Values come from `skillopfor.cfg`, which the content installer links in.
- `of_cvars.cpp`: OF cvars its code reads, fixed at their defaults.
- `rope_player.cpp`: the rope block of OF's `CBasePlayer::PreThink`, called
  from `sdk.patch`'s `player.cpp`.

Entities that need a class private to a Valve file live in `sdk.patch`
instead: `env_warpball` (`effects.cpp`), `env_spritetrain` (`plats.cpp`),
`trigger_xen_return`, `trigger_geneworm_hit` and the displacer targets
(`triggers.cpp`).
