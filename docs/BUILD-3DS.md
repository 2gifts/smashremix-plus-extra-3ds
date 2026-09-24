# Remix +EXTRA development setup

The full native gameplay integration is unfinished. These instructions build the pinned **N64 reference mod**, asset diagnostics, and a separate **fighter integration test CIA**. The full-mod release packager remains disabled.

## Requirements

- Windows, Git, and Python 3.12 or newer.
- Your own unmodified Super Smash Bros. US 1.0 ROM in big-endian `.z64` format. SHA-1: `e2929e10fccc0aa84e5776227e798abc07cedabf`.
- A host C++17 compiler for the asset-loader tests.
- For ARM11 diagnostics, the existing [3DS port toolchain](https://github.com/2gifts/smash64-3ds/blob/v1.0.1/docs/BUILD-3DS.md), configured in the ignored `3ds/build-config.json`.

## Check out the sources

```powershell
git clone --recursive https://github.com/2gifts/smashremix-plus-extra-3ds.git
cd smashremix-plus-extra-3ds
python -m venv remix/.venv
remix/.venv/Scripts/python.exe -m pip install -r remix/requirements-build.txt
remix/.venv/Scripts/python.exe remix/tools/inventory.py
```

For an existing checkout, run `git submodule update --init --recursive`. Do not update the dependencies to their latest branches independently: +EXTRA requires its pinned Remix revision, recorded in `remix/upstream.lock.json`.

## Build a local reference

```powershell
remix/.venv/Scripts/python.exe remix/tools/build_reference.py --rom "C:/path/to/your/Super Smash Bros. (USA).z64"
remix/.venv/Scripts/python.exe remix/tools/extract_reference_assets.py
```

The reference builder verifies the ROM and source revisions, exports both upstream projects to a fresh `remix/build/reference-*` directory, and runs their tools there. This is necessary because the upstream generator replaces `src/` and `build/`; running it in the native repository root would overwrite the decompiled engine.

Generated ROMs, symbols, extracted assets, and logs remain in ignored build directories. `remix/build/reference.json` identifies the current result and its hashes.

The asset conversion writes `remix/build/assets/reloc.reference.pak` plus a manifest. **Exit code 2 means conversion finished but relocation compatibility issues remain.** Inspect `relocation_issues` in the manifest. The pack is retained for analysis and raw-I/O testing; it is not approved for loading into the native game. Invalid ROM bounds, truncated tables, and other structural failures stop conversion immediately.

The importer recognizes raw `G_ENDDL` animation files whose upstream table incorrectly labels word zero as an internal relocation, and records each one under `normalized_display_lists`. It preserves their payloads and clears only the native pack's false relocation header. It also models the original loader's aligned, depth-first dependency allocations. If an external pointer crosses into a later file at the same target under every load-root context, the importer rewrites that pointer to the actual owning file and offset. Each rewrite appears under `canonicalized_cross_file` with both original and resolved IDs. Ambiguous or unmapped pointers remain in `relocation_issues` and still block full-pack relocation use. For an out-of-file internal pointer, `load_contexts` records candidate owning files and the roots where the target is absent. A candidate in only some roots is diagnostic, not a valid rewrite. This analysis runs across all 7,564 files, without a fighter-specific exception list.

## Test the loader

```powershell
remix/.venv/Scripts/python.exe remix/tools/test_asset_loader.py --reference
remix/.venv/Scripts/python.exe 3ds/tools/build_support.py
remix/.venv/Scripts/python.exe remix/tools/build_asset_probe.py
```

The host test accepts `--compiler` if a compiler is not configured. Without `--reference`, it uses only synthetic fixtures and requires no ROM or upstream assets.

The ARM11 diagnostic is `remix/build/asset-probe/remix-asset-probe.3dsx`. In Azahar it checks every asset payload and dependency count against checksums, using the real native loader. Its bottom-screen status is `00000002` on success. It runs raw file I/O only: it does not execute relocations or establish gameplay, 3D correctness, or hardware frame rate. It contains locally extracted assets and must remain local.

## Native game build

See [PORTING-STATUS.md](PORTING-STATUS.md). `3ds/tools/build_release.py` and `3ds/tools/package.py` stop while the native target is marked unfinished. The eventual application uses title ID `000400000ff64100` and `/3ds/ssb64-remix-extra/`, separate from the original port. Do not copy the original port's save into that folder: the expanded save layout still needs integration.

To audit the assembled fighter table and generate local ARM motion-data candidates:

```powershell
remix/.venv/Scripts/python.exe remix/tools/audit_reference_fighters.py
remix/.venv/Scripts/python.exe remix/tools/prepare_fighter_catalog.py
remix/.venv/Scripts/python.exe remix/tools/verify_fighter_catalog.py
```

These commands use the pinned local reference ROM. Generated `.inc` files stay under ignored `remix/build/fighter-catalog/` and are not linked into the game automatically. The report distinguishes script and asset structure from native gameplay implementation.

The motion-script decoder records compiled null subroutine operands as script stops, since the native event loop resolves them to null and ends that stream. The three Game & Watch variants now pass structural extraction. Spider-Man's two `SetDamageThrown` operands (`04000001` and `04000004`) remain unsupported and fail closed; the parser does not reinterpret them as ordinary waits.

## Adding a fighter to the native development build

The pinned Remix `src/Character.asm` uses `define_character`, action-parameter patches, and `table_patch_start` to build fighter records. The native importer reads the assembled results instead of replaying nested armips macros. `remix/tools/audit_reference_fighters.py` checks all 88 fighters' scripts and asset dependencies, then compares every five-word special-action record with the matching parent in the exact original ROM. `remix/build/action-callback-worklist.json` groups mod-owned callback targets by reference symbol and every fighter/status that uses them, so shared functions can be ported once. `remix/tools/reference_table_patches.py` discovers verified fixed-width Character tables from their assembled symbols and writes `remix/build/fighter-table-patches.json`, covering the full roster in one pass. It skips ambiguous table layouts rather than guessing. The native builder currently applies compiled costume, entry-action, and down-bound sound rows through shared registration; other table changes are visible in that manifest but still need native consumers.

The table extractor reads row widths from the pinned assembly's `move_table`, `table_patch_start`, and direct `scope` declarations, then bounds-checks them against the final ROM. `remix/tools/native_action_patches.py` maps original callback addresses to native C functions from decomp address comments and uses [`remix/native_callback_bindings.json`](../remix/native_callback_bindings.json) for explicit expansion-code bindings. Each address is bound once, then used wherever the assembled action table calls it. Falco's status assignments are generated through this path. An added status, changed action flags, stale symbol, or unbound callback fails generation until its native behavior is supplied. Most expansion callbacks are not bound yet.

`remix/tools/native_variant_metadata.py` reads the assembled `variant_original`, `variant_type`, and `variants_with_same_model` tables for every compiled fighter ID. It checks all added-fighter rows against the table patch report and emits a private ARM include. The bottom-screen portrait fallback uses the compiled original ID when it names a vanilla fighter; native accessors retain the type and same-model peers for the expanded character select. `remix/tools/emulator_variant_metadata.py` compares every generated row with the stereo Azahar executable. This table import does not implement the expanded character-select screen or make an unregistered fighter playable.

For repeated mod callbacks, `classify_action_callbacks.py` groups compiled instruction shapes and their users. `native_transition_templates.py` checks collision wrappers and translates recognized status changes and symbol-bounded status tables into shared native C. It also verifies the full conditional landing/cliff wrapper used by Sonic and Knuckles variants and requires an independent decoder to agree with its landing transition. Its straight-line decoder accepts an explicitly computed current or zero start frame and requires the fifth status argument to be initialized; a missing preserve-flags write remains unbound. `native_fkind_branch_transitions.py` symbolically follows bounded fighter-kind branches and requires every path to reach the same side-effect sequence; two independent exact patterns cross-check its output. `native_anim_end_templates.py` checks both the animation-end wrapper and its transition before generating native code, including decoded motion-flag resets. `native_guarded_original_callbacks.py` recognizes the complete compiled motion-flag guard before the original Captain Falcon turn routine and emits a shared native callback for every observed comparison value. `native_ground_walk_physics.py` decodes the signed speed and friction constants in the common ground-walk physics sequence and retains its two original engine calls. The generated manifests and `native-callback-coverage.json` show exactly which compiled addresses are bound. `native-callback-frontier.json` ranks the remaining addresses by instruction shape, table uses, and possible callback-only roster unlocks so the next shared decoder can be chosen by impact. Shapes are only planning hints; extend a checked family after confirming every MIPS side effect and keep unknown routines unbound. Fighter registration then consumes the resulting bindings automatically.

`native_special_dispatch.py` now reads all six compiled special-entry tables and deduplicates their target routines across fighters. Its restricted decoder accepts only fully modeled status-entry calls and motion-flag resets, emits a shared native handler for each accepted address, and writes `remix/build/native-special-dispatch.json` with unresolved instruction-shape groups. A fighter with any unbound special entry remains outside the generated roster. The current pinned ROM has 257 changed table slots and 181 distinct targets; 11 targets match this initial translator. This is an importer framework, not full special-move support. The action-callback generators also write one `native-generated-action-bindings.json` manifest consumed by the emulator pointer checks.

The projectile importer also recognizes the pinned `Fireball.add_to_character` macro. [`remix/tools/native_fireball_patches.py`](../remix/tools/native_fireball_patches.py) checks both normal and Kirby-copy table thunks, decodes the selected 48-byte physics record, and emits native profiles and a fighter-ID lookup. This supplies Japanese Mario and Japanese Luigi's projectile physics without per-fighter C branches. The same extraction records Dr. Mario and Dr. Luigi; Dr. Luigi is now in the development fixture, but its capsule effects and move behavior still need direct validation before release. Piano's independent fireball patch is reported separately because it does not use this macro.

[`remix/tools/native_kirby_patches.py`](../remix/tools/native_kirby_patches.py) imports the assembled 12-byte Kirby inhale rows for all expanded fighters. The native thrown-star path now uses their damage values instead of indexing Kirby's 27-row vanilla asset with an expanded fighter ID. Copy powers and hats still use the parent fallback until the expanded Kirby graphics and special-move callbacks have native implementations; decoding the metadata alone does not make those powers playable.

`remix/build/native-patch-worklist.json` groups every changed table across the roster, marks exactly which fighters have a native importer for that table, and lists the remaining table families to review per fighter. Use it with `action-callback-worklist.json` to choose the next shared native subsystem by impact. The worklist is a coverage report, not a claim that a fighter is playable.

`remix/tools/native_stage_tables.py` takes the same compiled-ROM approach for stages. It derives the 233-row count from three independent table boundaries, cross-checks original stage headers and setup pointers against the unmodified ROM, and imports every stage header, setup classification, class, default music override, and alternate track list in one pass. The development asset pack adds each stage header's transitive file dependencies after rejecting unresolved relocations. The native runtime accepts only no-hazard clones and original setup functions; an expansion-owned setup function fails closed until its behavior is translated. A private `--stage-id` Azahar option can exercise a compiled stage without claiming that the original stage-select menu exposes it. Default music overrides use the compiled track ID; alternate track selection still needs porting.

For the pinned reference, the table manifest covers 70 per-fighter tables. `sound_type_J` is a separate hit-sound table, so it is excluded from the per-fighter extractor. The original-address resolver finds 119 of 123 distinct non-null vanilla callback targets used by modified or added actions; it skips conflicting decomp address comments and functions whose C signature is incompatible with a status callback.

For a validated fighter, add one record to [`remix/native_fighters.json`](../remix/native_fighters.json), with its reference fighter ID, vanilla parent, and `registration` set to `generic` when its compiled action callbacks all have native bindings. The shared importer generates its action-table delta, including added statuses; a separate fighter-specific registrar is unnecessary. This catalog is a release gate after shared patch families and move behavior are implemented and emulator-tested. Keep `custom` for fighters with native behavior outside the shared registrar. Run:

```powershell
remix/.venv/Scripts/python.exe remix/tools/native_fighter_catalog.py
remix/.venv/Scripts/python.exe remix/tools/test_fighter_import.py
remix/.venv/Scripts/python.exe -m unittest discover -s remix/tools -p test_native_stage_tables.py
remix/.venv/Scripts/python.exe remix/tools/build_fighter_probe.py
```

The builder checks every enabled name, ID, parent, script, and asset closure against the pinned reference audit. For `generic` registrations it copies the native parent action table, applies compiled flag and callback changes, and appends added statuses. An unbound callback fails the build; a bound table still needs emulator move testing before its fighter can be considered complete. The builder also generates motion/script data, compiled costume patches, shared native registration, bottom-screen labels, and the VS bottom-card cycle. Character-specific MIPS functions cannot execute on ARM11; their native implementations and emulator move tests remain necessary. The catalog, generator, and shared runtime are source-only; generated ROM-derived includes and the CIA stay local.

To test candidates in batches without editing the source roster, use the opt-in development mode:

```powershell
remix/.venv/Scripts/python.exe remix/tools/build_fighter_probe.py --auto-bindable
remix/.venv/Scripts/python.exe remix/tools/emulator_auto_roster.py
```

This derives a private roster from the current compiled audit and native callback bindings. It requires validated fighter assets and scripts, a known vanilla parent, every action callback bound to ARM code, and every changed special-entry dispatch target translated to ARM. The pinned build currently adds eleven structural candidates to the 19-fighter fixture. The builder writes ignored `auto-roster.json` and `auto-roster-report.json`, then packages `3ds/build/falco-test/Remix-Auto-Bindable-Test.cia`; the emulator runner restarts Azahar for each candidate and writes an ignored per-candidate result. Ness-derived fighters now keep the original Ness effect model loaded alongside their own fighter files, because the common PK Thunder effect descriptor uses a fixed offset that is invalid in Lucas's model. Lucas reached a stereo results scene after this fix. The build and smoke tests identify shared runtime gaps; they do not prove full movesets or make the candidates release-ready. This CIA uses the same development title ID as the ordinary fighter test, so installing either replaces the other.

The shared hit-sound importer reads all 88 compiled `sound_type` rows and the assembled Japanese sound-ID table. It validates the IDs against the packaged FGM bank and applies the Japanese table at the common fighter-hit playback path for J-type attackers. This reproduces Remix's default per-fighter sound selection; the mod's Japanese-sounds override menu is not yet native.

## Build the fighter development CIA

Complete the reference extraction above and configure the existing 3DS toolchain. Set `vanilla_assets` in the ignored `3ds/build-config.json` to the asset directory produced by the original 3DS port's local build. It needs `reloc.pak`, `audio/`, `particles/`, `initial-save.bin` and `bottom-ui.bin`. If omitted, the tool looks for `assets/` two directories above the configured BattleShip checkout, matching the original port's `3ds/vendor/BattleShip` layout.

To start with your own unlocked original-game fighters, set `save` in the same ignored config to your `.srm` path. The builder validates its signature and checksum, converts it locally, and packages it as the initial save after preparing the fighter assets. If omitted, it packages the base asset directory's initial save. Existing `/3ds/ssb64-remix-falco-test/save.bin` and `save.bak` on the SD card take precedence over the packaged initial save.

```powershell
remix/.venv/Scripts/python.exe remix/tools/test_fighter_import.py
remix/.venv/Scripts/python.exe remix/tools/build_fighter_probe.py
```

Output: `3ds/build/falco-test/Remix-Fighter-Integration-Test.cia`. The accompanying `package/verified.json` verifies the CIA content against the linked executable and private RomFS, checks its title/capabilities, and checks that scripted controls, automatic screenshots, verbose logs and the debugger boot gate are disabled for ordinary use.

With Azahar configured for the local development build, run `remix/.venv/Scripts/python.exe remix/tools/emulator_variant_metadata.py` to compare the generated variant table with the linked stereo executable. The private result is `remix/build/fighter-probe/variant-metadata-emulator.json`.

To test on a homebrewed **New Nintendo 3DS / New 3DS XL**, copy this local CIA to the SD card and install it with FBI. Launch **Remix fighter test**, enter VS mode, select **Fox**, **Samus**, **Link**, **Yoshi**, **Ness**, **Pikachu**, **Jigglypuff**, **Mario**, **Captain Falcon**, **Luigi**, or **Donkey Kong** on the top screen, then tap that player's bottom-screen card. Fox, Yoshi, Ness, Mario, Captain Falcon, and Luigi toggle to **Falco**, **J Yoshi**, **J Ness**, **J Mario**, **J Falcon**, and **J Luigi**. The Samus card cycles through **J Samus**, **E Samus**, and ordinary Samus; Donkey Kong cycles through **DK Ult**, **J DK**, and ordinary Donkey Kong; Pikachu cycles through **J Pika**, **E Pika**, and ordinary Pikachu; Link cycles through **E Link**, **J Link**, and ordinary Link; Jigglypuff cycles through **J Puff**, **E Puff**, and ordinary Jigglypuff. The bottom card names the imported fighter, while the original top-screen portrait and announcer still use the vanilla parent. Training and other modes do not have this selector. The existing 3D slider, display toggle and control options are available.

The test uses title ID `000400000ff64200`, product code `CTR-P-SMFT`, and `/3ds/ssb64-remix-falco-test/`. It installs alongside the original game and replaces earlier fighter-development builds. It contains the original menus and stages, not the full Remix/+EXTRA roster or engine. CPU behavior and all modes have not been fully validated for the imported fighters. See [fixture limits](PORTING-STATUS.md#fighter-fixture-limits).

The CIA contains locally extracted assets and stays local. Do not upload it with source contributions. A debugger-oriented 3DSX can also be linked with `SSB_REMIX_PROBE=falco` and `3ds/tools/build_runtime.py --render`; that variant waits for a harness and is not the normal hardware test build.
