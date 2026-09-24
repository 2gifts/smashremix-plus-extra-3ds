# Smash Remix +EXTRA for New Nintendo 3DS

A native 3DS port **in development**, derived from [Smash 64 for New Nintendo 3DS](https://github.com/2gifts/smash64-3ds). The target is the complete [Smash Remix](https://github.com/JSsixtyfour/smashremix) base with [Smash Remix +EXTRA](https://github.com/joaorb64/smashremix-plus-extra), retaining the existing port's stereoscopic rendering, widescreen option, bottom-screen HUD, and control settings.

**The complete Remix +EXTRA port is not ready.** A local development CIA offers native Falco, Japanese Fox, Japanese Pikachu, Electric Pikachu, Japanese Samus, Electric Samus, Electric Link, Japanese Link, Japanese Yoshi, Japanese Ness, Japanese Mario, Japanese Captain Falcon, Japanese Luigi, Dr. Luigi, Metal Luigi, Japanese Donkey Kong, Japanese Jigglypuff, Electric Jigglypuff, and +EXTRA's DK Ult in VS mode. Select a vanilla parent on the top screen, then tap that player's bottom-screen card to switch fighters. The Fox card cycles through Falco, J Fox, and ordinary Fox; the Donkey Kong card cycles through DK Ult, J DK, and ordinary DK; the Luigi card cycles through J Luigi, Dr. Luigi, Metal Luigi, and ordinary Luigi; the Pikachu card cycles through J Pika, E Pika, and ordinary Pikachu; the Samus card cycles through J Samus, E Samus, and ordinary Samus; the Link card cycles through E Link, J Link, and ordinary Link; the Jigglypuff card cycles through J Puff, E Puff, and ordinary Jigglypuff. This tests nineteen imported fighters, not the expanded roster or finished mod. The original Smash 64 port remains available in its [own repository](https://github.com/2gifts/smash64-3ds).

## Current progress

- Complete history of the native 3DS port, starting from v1.0.1.
- Pinned +EXTRA **0.6.0** and its required **Remix 2.0.1** source revision.
- Reproducible local reference-ROM build using your own US 1.0 ROM.
- Expanded native asset loader with bounded caching for the larger mod catalogue.
- Asset conversion checks, host regression tests, and an ARM11 asset diagnostic.
- Nineteen native fighter integration paths in the development build. Falco, DK Ult, and Japanese Pikachu have dedicated native move logic; the shared importer covers the other catalogued variants, including Dr. Luigi and Metal Luigi. Earlier variants have targeted move checks; the newest two have stereo match-to-results smoke tests, not complete moveset parity.
- One [validated fighter catalog](remix/native_fighters.json) drives the temporary selector, ROM-derived motion/script extraction, asset closure, and shared native registration. The build generates native action tables for generic fighters whose compiled callbacks all have native bindings, and rejects unbound callbacks. Custom move logic remains native C; see the [contribution workflow](docs/BUILD-3DS.md#adding-a-fighter-to-the-native-development-build).
- The compiled patch importer now reports shared MIPS callback dependencies across the entire roster, ranking the native engine interfaces and expansion helpers needed by unbound actions. This guides reusable translation work instead of choosing one fighter at a time; it does not make additional fighters playable by itself.
- A guarded original-code clone importer recognizes every compiled copy of Mario's up-special collision routine that changes only landing lag, generating shared native handlers for 17 callbacks used in 61 action-table slots. Falco's former hand-written copy uses this importer too.
- A source-copy inventory now links upstream `OS.copy_segment` uses to their compiled callback consumers, and a checked aerial-drift adapter imports Goemon's shared speed override for 15 action-table slots.
- Expanded sound-bank conversion with validated pointers and unchanged sample payloads.
- Shared import of Remix's compiled per-fighter Japanese hit-sound selection and sound IDs; the mod's sound-override menu is still pending.
- Separate application identity and save directory for the eventual 3DS build.

Remix adds N64 assembly code as well as characters and assets. Its fighter registry, new moves, engine patches, menus, and save layout still need native integration. See [porting status](docs/PORTING-STATUS.md) for what is tested and what remains.

## Building and contributing

See the [development build guide](docs/BUILD-3DS.md) to build the reference mod, run checks, or build the fighter test CIA from your own assets. Its HOME Menu label is **Remix fighter test**; in VS mode, tap the Fox, Samus, Yoshi, Mario, Captain Falcon, or Luigi bottom-screen card for its imported counterpart, or cycle the Donkey Kong, Pikachu, and Link cards through their imported variants. The full-mod release packager remains disabled while integration is unfinished.

The target hardware is **New Nintendo 3DS / New 3DS XL**. Gameplay performance and stereo compatibility for Remix are not established yet.

ROMs, extracted assets, saves, firmware, and compiled game binaries stay local. Please submit source changes and reproducible bug reports, with upstream revisions and the affected character or stage. Preserve upstream author notes when porting code or importing content.

## Credits

- [VetriTheRetri/ssb-decomp-re](https://github.com/VetriTheRetri/ssb-decomp-re) and its contributors — original game decompilation.
- [Smash Remix](https://github.com/JSsixtyfour/smashremix), organized by **The_Smashfather**, and its full team — expanded game, characters, stages, tools, and engine work.
- [João Ribeiro Bezerra / joaorb64 and the +EXTRA contributors](https://github.com/joaorb64/smashremix-plus-extra) — the extra-content engine and community content.
- [2gifts/smash64-3ds](https://github.com/2gifts/smash64-3ds), [JRickey's BattleShip](https://github.com/JRickey/BattleShip), the [SM64 3DS graphics backend](https://github.com/mkst/sm64-port/tree/3ds-port), and the 3DS homebrew toolchain contributors — the native-port foundation.

[Full attribution and upstream credit links](CREDITS.md). Original contributor notices and component licenses are retained. This is an independent fan port, not an official Smash Remix or +EXTRA release and not affiliated with Nintendo or HAL Laboratory.
