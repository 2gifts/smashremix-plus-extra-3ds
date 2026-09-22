# Native port status

The project starts from the console-tested Smash 64 3DS port, v1.0.1. Remix +EXTRA is **not playable on the 3DS yet**. This repository is the separate development project; the original game's working release is unchanged.

## Implemented and checked

- Full port history retained, including stereoscopic rendering, widescreen, bottom-screen UI, controls, and previous fixes.
- +EXTRA 0.6.0 and its exact Remix dependency pinned as nested submodules.
- A local, isolated upstream build completed from the US 1.0 ROM: 80,421,504-byte N64 reference output.
- Conversion and inspection of all 7,564 relocation assets: 82,246,242-byte reference pack.
- Native loader accepts expanded file tables, validates index bounds and dependency IDs, and streams large packs instead of allocating the entire catalogue on the 3DS heap. Small packs retain the original resident fast path. The decoded-file cache remains bounded to 1 MiB.
- Host checks verify all reference payloads, expanded IDs, bounded caching, reopening, and malformed-index rejection. ARM11 support compilation succeeds. Existing controls, display, and performance-report tests pass.
- The ARM11 diagnostic passed in Azahar, reading and checksum-verifying all 7,564 payloads. This is a raw-asset test, not a match or frame-rate measurement.
- Separate application ID and SD paths are assigned. No shared saves or settings with the original port.

## Remaining native integration

1. **Fighters and engine patches.** The original C engine has the vanilla fighter tables. Remix supplies an expanded registry, action tables, callbacks, items, AI, and engine hooks in N64 MIPS assembly. These must be translated or mapped to native C implementations, with correct ARM structures and pointers. The inventory records 404 base Remix assembly files and 1,969 patch calls; +EXTRA adds 19 fighter definitions, including variants, and additional code.
2. **Movesets and relocation semantics.** The current conversion flags 32 relocation compatibility issues across 23 files, including character main files, turnip graphics, and Game & Watch end images. These are observations from the native validator, not a claim that all those files are broken in the upstream N64 game. Resolve their intended usage before applying native pointer fixups; do not silence the checks or pad invalid targets into apparently valid memory.
3. **Menus, stages, sound and saves.** Integrate expanded selection menus, mod stage loading and callbacks, audio banks, and the mod's save data. Preserve original and mod credits. The reference builder includes the entire base mod; it is not limited to +EXTRA's character folders.
4. **Gameplay validation.** Exercise actual new-character moves, projectiles, collisions, KO/results, single-player transitions, and credits in the 3DS emulator. Then measure memory use and frame times on New 3DS hardware, including four fighters and stereo. The original port's performance does not establish Remix performance.

The default release commands stop until that integration is ready, so a vanilla game with a Remix label cannot be mistaken for a completed port. No playable Remix CIA or release tag has been published.

## Reproducing the evidence

[Build instructions](BUILD-3DS.md) generate these local reports:

- `remix/build/inventory.json`: source counts and per-character provenance.
- `remix/build/reference.json`: pinned source revisions and reference ROM hash.
- `remix/build/assets/manifest.json`: per-file hashes and relocation findings.
- `remix/build/loader-test/verified.json`: expanded-loader checks.
- `remix/build/asset-probe/build.json`: raw-asset diagnostic build hashes.

These reports describe their test scope. Raw asset reads and compilation are not gameplay tests.

A source-only [verification summary](../remix/verification.json) records the checked revisions, hashes, test scope, and remaining relocation findings.
