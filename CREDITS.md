# Credits and provenance

This project ports existing work to New Nintendo 3DS. Authorship of the original game, decompilation, Remix, +EXTRA, and individual characters, stages, animations, audio, and tools remains with their creators.

| Contribution | Upstream project and credits |
| --- | --- |
| Original game | Nintendo and HAL Laboratory; the original in-game credits |
| Decompilation | [VetriTheRetri/ssb-decomp-re](https://github.com/VetriTheRetri/ssb-decomp-re) and [contributors](https://github.com/VetriTheRetri/ssb-decomp-re/graphs/contributors) |
| Native 3DS foundation | [2gifts/smash64-3ds v1.0.1](https://github.com/2gifts/smash64-3ds/tree/v1.0.1); its complete commit history is retained here |
| Native engine, asset and audio bridges | [JRickey/BattleShip](https://github.com/JRickey/BattleShip), including the port-patches work and contributors |
| Smash Remix | [JSsixtyfour/smashremix](https://github.com/JSsixtyfour/smashremix), organized by The_Smashfather; [full in-game credit list](https://github.com/JSsixtyfour/smashremix/blob/5e04fe7fcd023cd43c71f25f89bb6e810d254d55/src/Credits.asm) and [contributors](https://github.com/JSsixtyfour/smashremix/graphs/contributors) |
| Falco native integration fixture | Fray's [Phantasm implementation](https://github.com/JSsixtyfour/smashremix/blob/5e04fe7fcd023cd43c71f25f89bb6e810d254d55/src/Falco/Phantasm.asm) and Remix's [motion commands](https://github.com/JSsixtyfour/smashremix/blob/5e04fe7fcd023cd43c71f25f89bb6e810d254d55/src/Command.asm), translated to native C; model, animation and sound authors retain their original credits in the Remix project |
| Smash Remix +EXTRA | [joaorb64/smashremix-plus-extra](https://github.com/joaorb64/smashremix-plus-extra), João Ribeiro Bezerra and the [contributors](https://github.com/joaorb64/smashremix-plus-extra/graphs/contributors); individual source comments and content notes are preserved in the pinned submodule |
| ROM tables and VPK decoding used by the reference importer | Zoinkity's [Super Smash Bros. File Inserter / SSB.py](https://github.com/joaorb64/smashremix-plus-extra/blob/d981b7c23d7aadb80f86aadb6fbe7d9519a33ab4/SSB.py), as maintained in +EXTRA |
| Graphics backend | [mkst/sm64-port, 3ds-port](https://github.com/mkst/sm64-port/tree/3ds-port), and its upstream contributors |
| 3DS toolchain and libraries | [devkitPro](https://devkitpro.org/), [libctru](https://github.com/devkitPro/libctru), [citro3d](https://github.com/devkitPro/citro3d), and the 3DS homebrew community |
| Emulator testing | [Azahar](https://github.com/azahar-emu/azahar) and its upstream contributors |

The linked Remix credits include artists, musicians, animators, programmers, testers, and other contributors who may not appear in Git history. For +EXTRA content, consult the [character sources](https://github.com/joaorb64/smashremix-plus-extra/tree/d981b7c23d7aadb80f86aadb6fbe7d9519a33ab4/extra_characters), [stage sources](https://github.com/joaorb64/smashremix-plus-extra/tree/d981b7c23d7aadb80f86aadb6fbe7d9519a33ab4/extra_stages), and [audio sources](https://github.com/joaorb64/smashremix-plus-extra/tree/d981b7c23d7aadb80f86aadb6fbe7d9519a33ab4/extra_music) alongside its contributor history. These links complement the per-file credits; they do not replace them.

Exact source revisions are recorded in [remix/upstream.lock.json](remix/upstream.lock.json). Keep upstream headers and author notes when translating assembly into C, and add the original source path and revision to the translated file. Credit new ports separately from the original design, code, and content. Preserve the original and mod in-game credits when their native implementation is integrated.

Existing licenses and notices remain in [3ds/licenses](3ds/licenses) and the upstream submodules. No blanket license is applied to other contributors' work. The graphics dependency's source-only distribution condition is retained; this repository publishes source and build tools, not game packages or extracted assets. Character names, music, artwork, and other original material remain the property of their respective owners.
