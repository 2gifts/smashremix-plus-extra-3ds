# Remix +EXTRA development setup

The native gameplay integration is unfinished. These instructions build the pinned **N64 reference mod** and asset diagnostics. They do not produce an installable Remix game. The inherited release packager refuses to label the vanilla engine as Remix.

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
