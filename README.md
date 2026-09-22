# Smash Remix +EXTRA for New Nintendo 3DS

A native 3DS port **in development**, derived from [Smash 64 for New Nintendo 3DS](https://github.com/2gifts/smash64-3ds). The target is the complete [Smash Remix](https://github.com/JSsixtyfour/smashremix) base with [Smash Remix +EXTRA](https://github.com/joaorb64/smashremix-plus-extra), retaining the existing port's stereoscopic rendering, widescreen option, bottom-screen HUD, and control settings.

**Remix gameplay does not run on 3DS yet. There is no playable Remix CIA available from this repository.** The original Smash 64 port remains available in its [own repository](https://github.com/2gifts/smash64-3ds).

## Current progress

- Complete history of the native 3DS port, starting from v1.0.1.
- Pinned +EXTRA **0.6.0** and its required **Remix 2.0.1** source revision.
- Reproducible local reference-ROM build using your own US 1.0 ROM.
- Expanded native asset loader with bounded caching for the larger mod catalogue.
- Asset conversion checks, host regression tests, and an ARM11 asset diagnostic.
- Separate application identity and save directory for the eventual 3DS build.

Remix adds N64 assembly code as well as characters and assets. Its fighter registry, new moves, engine patches, menus, and save layout still need native integration. See [porting status](docs/PORTING-STATUS.md) for what is tested and what remains.

## Building and contributing

See the [development build guide](docs/BUILD-3DS.md). The current tools produce a reference N64 ROM and diagnostics; they do not produce a playable Remix CIA. The release packager checks this explicitly.

The target hardware is **New Nintendo 3DS / New 3DS XL**. Gameplay performance and stereo compatibility for Remix are not established yet.

ROMs, extracted assets, saves, firmware, and compiled game binaries stay local. Please submit source changes and reproducible bug reports, with upstream revisions and the affected character or stage. Preserve upstream author notes when porting code or importing content.

## Credits

- [VetriTheRetri/ssb-decomp-re](https://github.com/VetriTheRetri/ssb-decomp-re) and its contributors — original game decompilation.
- [Smash Remix](https://github.com/JSsixtyfour/smashremix), organized by **The_Smashfather**, and its full team — expanded game, characters, stages, tools, and engine work.
- [João Ribeiro Bezerra / joaorb64 and the +EXTRA contributors](https://github.com/joaorb64/smashremix-plus-extra) — the extra-content engine and community content.
- [2gifts/smash64-3ds](https://github.com/2gifts/smash64-3ds), [JRickey's BattleShip](https://github.com/JRickey/BattleShip), the [SM64 3DS graphics backend](https://github.com/mkst/sm64-port/tree/3ds-port), and the 3DS homebrew toolchain contributors — the native-port foundation.

[Full attribution and upstream credit links](CREDITS.md). Original contributor notices and component licenses are retained. This is an independent fan port, not an official Smash Remix or +EXTRA release and not affiliated with Nintendo or HAL Laboratory.
