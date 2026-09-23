# Remix +EXTRA development setup

The full native gameplay integration is unfinished. These instructions build the pinned **N64 reference mod**, asset diagnostics, and a separate **Falco integration test CIA**. The full-mod release packager remains disabled.

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

## Build the Falco development CIA

Complete the reference extraction above and configure the existing 3DS toolchain. Set `vanilla_assets` in the ignored `3ds/build-config.json` to the asset directory produced by the original 3DS port's local build. It needs `reloc.pak`, `audio/`, `particles/`, `initial-save.bin` and `bottom-ui.bin`. If omitted, the tool looks for `assets/` two directories above the configured BattleShip checkout, matching the original port's `3ds/vendor/BattleShip` layout.

```powershell
remix/.venv/Scripts/python.exe remix/tools/test_fighter_import.py
remix/.venv/Scripts/python.exe remix/tools/build_fighter_probe.py
```

Output: `3ds/build/falco-test/Remix-Falco-Integration-Test.cia`. The accompanying `package/verified.json` verifies the CIA content against the linked executable and private RomFS, checks its title/capabilities, and checks that scripted controls, automatic screenshots, verbose logs and the debugger boot gate are disabled for ordinary use.

To test on a homebrewed **New Nintendo 3DS / New 3DS XL**, copy this local CIA to the SD card and install it with FBI. Launch **Remix Falco test** and select **Fox** in training or versus mode. Falco occupies that slot. The bottom screen names him Falco; the original selection portrait and announcer still say Fox. The existing 3D slider, display toggle and control options are available.

The test uses title ID `000400000ff64200`, product code `CTR-P-SMFT`, and `/3ds/ssb64-remix-falco-test/`. It installs alongside the original game. It contains the original menus and stages, not the full Remix/+EXTRA roster or engine. CPU behavior and all modes have not been fully validated for the replacement fighter. See [fixture limits](PORTING-STATUS.md#falco-fixture-limits).

The CIA contains locally extracted assets and stays local. Do not upload it with source contributions. A debugger-oriented 3DSX can also be linked with `SSB_REMIX_PROBE=falco` and `3ds/tools/build_runtime.py --render`; that variant waits for a harness and is not the normal hardware test build.
