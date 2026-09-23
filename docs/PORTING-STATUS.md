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
- A Falco integration fixture has 219 main motions, 15 menu motions, 813 decoded motion words, 10 relocated script pointers, and a validated closure of 179 assets. It translates Phantasm movement into native C, applies Falco's Firebird adjustments, and implements the frame-speed and translation commands used by its scripts. Animation classification excludes the empty motion ID so shared menu sprites are not corrupted.
- Expanded SFX conversion resolves the mod's split ROM/RAM bank into native packages: 1,516 sounds/samples, 1,667 sound-table entries, and 1,924 microcode entries. Serialized pointer bounds and unchanged sample bytes are verified. Music remains the original game's bank.
- A separate, plainly labeled Falco test CIA starts without a debugger and uses title ID `000400000ff64200` and `/3ds/ssb64-remix-falco-test/`. Package checks verify its executable, assets and normal startup defaults. First-run save creation and backup recovery have regression coverage.
- A reference-table audit now identifies all 88 added fighter records, including the 19 +EXTRA records. It resolves original menu-script references to their native decomp symbols, decodes the expanded custom-command formats, and traces each fighter's asset dependencies. It can generate ARM-syntax-checked motion data for 69 records. This is data import only: those fighters remain disabled until native callbacks, roster presentation, and gameplay are integrated.
- The shared native command path now handles Remix and +EXTRA motion commands `D0`–`DE`, including per-hitbox hitlag and DI multipliers. These commands are compiled into the Falco fixture, but `DD`/`DE` still need gameplay validation with the +EXTRA fighters that use them. Mod-wide engine behavior remains unported.
- The ARM fighter registry now has an independently backed Falco row at the reference mod's fkind 29. The file-size and animation-heap prepass scans registered rows through fkind 127 and skips unused IDs. Falco can now be chosen in VS mode by selecting Fox on the original top-screen grid and tapping that player's bottom-screen card. A private Azahar harness used that touch path in a timed four-fighter stereo match, observed 39 action states, reached results, and returned to VS select without an invalid memory access. Leaving the card untouched still enters a match as native Fox (fkind 1). This is an initial selection bridge, not the expanded Remix character-select interface.
- The results scene now loads the main files for any registered extra fighters in the match before constructing their result-screen models. On return to VS select, Falco's ID maps back to the original Fox portrait while the bottom card preserves Falco as the next match choice.

## Remaining native integration

1. **Fighters and engine patches.** The original C engine has the vanilla fighter tables. Remix supplies an expanded registry, action tables, callbacks, items, AI, and engine hooks in N64 MIPS assembly. These must be translated or mapped to native C implementations, with correct ARM structures and pointers. The inventory records 404 base Remix assembly files and 1,969 patch calls; +EXTRA adds 19 fighter definitions, including variants, and additional code.
   The current audit finds 16 fighter dependency closures containing unresolved relocation records and four fighters with undecodable or null script targets. Structural import for other fighters does not establish correct moves, specials, or menu behavior.
2. **Movesets and relocation semantics.** The current conversion flags 32 relocation compatibility issues across 23 files, including character main files, turnip graphics, and Game & Watch end images. These are observations from the native validator, not a claim that all those files are broken in the upstream N64 game. Resolve their intended usage before applying native pointer fixups; do not silence the checks or pad invalid targets into apparently valid memory.
3. **Menus, stages, sound and saves.** Integrate expanded selection menus, mod stage loading and callbacks, audio banks, and the mod's save data. Preserve original and mod credits. The reference builder includes the entire base mod; it is not limited to +EXTRA's character folders.
4. **Gameplay validation.** Exercise actual new-character moves, projectiles, collisions, KO/results, single-player transitions, and credits in the 3DS emulator. Then measure memory use and frame times on New 3DS hardware, including four fighters and stereo. The original port's performance does not establish Remix performance.

The default release commands stop until that integration is ready. The separate Falco development packager does not change that status. No complete Remix CIA or release tag has been published.

## Falco fixture limits

Fox remains available. In VS mode, Falco is selected from the Fox portrait using the bottom-screen card and enters the match as fkind 29. The top-screen selection portrait, announcer and some presentation still refer to Fox. Training and other modes have not gained this selector. Menus, stages, items, music, save layout, the other fighters and AI are inherited from the original port. Remix-wide engine changes, Kirby's Falco copy ability, expanded selection screens and +EXTRA fighters are not implemented. This fixture establishes the first native integration path; it does not establish complete Falco parity or full-mod compatibility.

The packaged executable passed nine move checks in Azahar: grounded/airborne Phantasm, jab, down smash, reflector, Firebird, grab script/throw-pointer setup, taunt, and down aerial. It also passed startup with scripted controls disabled and a four-fighter stereo match through the results screen, with no invalid memory accesses or SD-write errors detected in that run. These are smoke tests, not complete move/interactions coverage. Details and matching package hashes are in `remix/verification.json`. Real-console performance is unmeasured; debugger-instrumented timing is not hardware frame-rate evidence.

## Reproducing the evidence

[Build instructions](BUILD-3DS.md) generate these local reports:

- `remix/build/inventory.json`: source counts and per-character provenance.
- `remix/build/reference.json`: pinned source revisions and reference ROM hash.
- `remix/build/assets/manifest.json`: per-file hashes and relocation findings.
- `remix/build/loader-test/verified.json`: expanded-loader checks.
- `remix/build/asset-probe/build.json`: raw-asset diagnostic build hashes.
- `remix/build/fighter-probe/manifest.json`: native fighter fixture scope and asset closure.
- `remix/build/fighter-audit.json`: all added fighter IDs, parents, command census, script findings, and asset closures.
- `remix/build/fighter-catalog/manifest.json`: generated native motion-data scope and syntax-check status; no new fighter is registered by this tool.
- `remix/build/audio/manifest.json`: expanded sound packages and validation counts.
- `3ds/build/falco-test/package/verified.json`: development package integrity and startup defaults.

These reports describe their test scope. Raw asset reads and compilation are not gameplay tests.

A source-only [verification summary](../remix/verification.json) records the checked revisions, hashes, test scope, and remaining relocation findings.
