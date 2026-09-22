"""Repack Remix's split ROM/RAM sound bank for the native audio synthesizer.

The N64 mod extends pointer-based banks into its injected code segment. Those
offsets cannot be used with the original contiguous native CTL blobs. Resolve
and validate every record, then emit compact self-contained CTL/TBL packages.
No assembly is executed and all output stays in the ignored local build tree.
"""
import struct
from common import BUILD, sha256, write_json
from prepare_fighter_probe import Reference


def u32(data, offset=0):
    return struct.unpack_from('>I', data, offset)[0]


class Bank:
    def __init__(self, ref, rom_base, ram_base, original_size, samples_base):
        self.ref, self.rom_base, self.ram_base = ref, rom_base, ram_base
        self.original_size, self.samples_base = original_size, samples_base
        self.ctl, self.tbl = bytearray(), bytearray()
        self.cache, self.samples = {}, {}

    def read(self, offset, size):
        if offset < 0 or size < 0:
            raise ValueError('Negative audio record range')
        if 0 <= offset and offset + size <= self.original_size:
            pos = self.rom_base + offset
        elif self.ref.ram_base <= self.ram_base + offset:
            pos = self.ram_base + offset - self.ref.ram_base + self.ref.rom_base
        else:
            raise ValueError(f'Unmapped bank pointer {offset:#x}')
        if pos < 0 or pos + size > len(self.ref.rom):
            raise ValueError('Audio record outside reference ROM')
        return self.ref.rom[pos:pos + size]

    def record(self, kind, offset):
        key = kind, offset
        if key in self.cache:
            return self.cache[key]
        head = self.read(offset, 8)
        count = None
        if kind == 'file':
            count = struct.unpack_from('>h', head, 2)[0]
            size, fields = 4 + 4 * count, [(4 + i * 4, 'bank') for i in range(count)]
        elif kind == 'bank':
            count = struct.unpack_from('>h', head)[0]
            size, fields = 12 + 4 * count, [(8, 'instrument')] + [(12 + i * 4, 'instrument') for i in range(count)]
        elif kind == 'instrument':
            count = struct.unpack_from('>h', self.read(offset, 16), 14)[0]
            size, fields = 16 + 4 * count, [(16 + i * 4, 'sound') for i in range(count)]
        elif kind == 'sound':
            size, fields = 16, [(0, 'envelope'), (4, 'keymap'), (8, 'wave')]
        elif kind == 'wave':
            head = self.read(offset, 20)
            if head[8] not in (0, 1):
                raise ValueError('Unsupported audio sample encoding')
            size, fields = 20, [(12, 'adpcmloop' if head[8] == 0 else 'rawloop')]
            if head[8] == 0:
                fields.append((16, 'book'))
        elif kind == 'book':
            order, predictors = struct.unpack('>II', head)
            if not (1 <= order <= 8 and 1 <= predictors <= 8):
                raise ValueError('Invalid ADPCM predictor book')
            size, fields = 8 + order * predictors * 16, []
        else:
            size, fields = {'envelope': 16, 'keymap': 8, 'adpcmloop': 44, 'rawloop': 12}[kind], []
        if count is not None and not 0 < count <= 4096:
            raise ValueError(f'Invalid {kind} count {count}')
        raw = bytearray(self.read(offset, size))
        result = len(self.ctl)
        self.cache[key] = result
        self.ctl.extend(raw)
        self.ctl.extend(bytes((-len(self.ctl)) % 4))
        for slot, child in fields:
            pointer = u32(raw, slot)
            if pointer:
                struct.pack_into('>I', self.ctl, result + slot, self.record(child, pointer))
        if kind == 'wave':
            start, length = struct.unpack_from('>II', raw)
            if not 0 < length <= 8 * 1024 * 1024:
                raise ValueError('Invalid sample length')
            if (start, length) not in self.samples:
                begin = self.samples_base + start
                if begin < 0 or begin + length > len(self.ref.rom):
                    raise ValueError('Sample beyond reference ROM')
                self.samples[start, length] = len(self.tbl)
                self.tbl.extend(self.ref.rom[begin:begin + length])
                self.tbl.extend(bytes((-len(self.tbl)) % 8))
            struct.pack_into('>I', self.ctl, result, self.samples[start, length])
        return result


def package(ref, base, ram_base, original_size, extension, end):
    """Preserve microcode bytes and relative branches; relocate table offsets."""
    if base < 0 or original_size < 4 or base + original_size > len(ref.rom):
        raise ValueError('Original audio package outside ROM')
    count = u32(ref.rom, base)
    if not 0 < count <= 8192 or 4 + count * 4 > original_size:
        raise ValueError('Invalid audio package count')
    ext_begin, ext_end = ref.symbols[extension], ref.symbols[end]
    if not ref.ram_base <= ext_begin < ext_end:
        raise ValueError('Invalid package extension range')
    output = bytearray(4 + 4 * count)
    struct.pack_into('>I', output, 0, count)
    orig_dest = len(output)
    output.extend(ref.rom[base:base + original_size])
    ext_dest = len(output)
    ext_rom = ext_begin - ref.ram_base + ref.rom_base
    if ext_rom < 0 or ext_rom + ext_end - ext_begin > len(ref.rom):
        raise ValueError('Extended audio package outside ROM')
    output.extend(ref.rom[ext_rom:ext_rom + ext_end - ext_begin])
    for i in range(count):
        offset = u32(ref.rom, base + 4 + i * 4)
        if offset < original_size:
            target = orig_dest + offset
        elif ext_begin <= ram_base + offset < ext_end:
            target = ext_dest + ram_base + offset - ext_begin
        else:
            raise ValueError(f'Audio package {i}: unrecognized pointer {offset:#x}')
        struct.pack_into('>I', output, 4 + i * 4, target)
    return output


def verify_bank(ctl, tbl):
    """Walk the serialized result independently, as the native consumer does."""
    seen, sounds, waves = set(), set(), set()
    def read(pos, length):
        if pos < 0 or pos % 4 or pos + length > len(ctl):
            raise ValueError('Repacked bank pointer outside CTL')
        return ctl[pos:pos + length]
    def visit(kind, pos):
        if (kind, pos) in seen:
            return
        seen.add((kind, pos))
        if kind == 'file':
            magic, count = struct.unpack('>HH', read(pos, 4))
            if magic != 0x4231 or not 0 < count <= 4096:
                raise ValueError('Invalid serialized bank header')
            slots = [(4 + i * 4, 'bank') for i in range(count)]
            length = 4 + count * 4
        elif kind == 'bank':
            count = struct.unpack_from('>H', read(pos, 12))[0]
            slots = [(8, 'instrument')] + [(12 + i * 4, 'instrument') for i in range(count)]
            length = 12 + count * 4
        elif kind == 'instrument':
            count = struct.unpack_from('>H', read(pos, 16), 14)[0]
            slots = [(16 + i * 4, 'sound') for i in range(count)]
            length = 16 + count * 4
        elif kind == 'sound':
            sounds.add(pos)
            length, slots = 16, [(0, 'envelope'), (4, 'keymap'), (8, 'wave')]
        elif kind == 'wave':
            raw = read(pos, 20)
            start, size = struct.unpack_from('>II', raw)
            if not size or start % 8 or start + size > len(tbl) or raw[8] not in (0, 1):
                raise ValueError('Invalid serialized sample range')
            waves.add(pos)
            length, slots = 20, [(12, 'adpcmloop' if raw[8] == 0 else 'rawloop')]
            if raw[8] == 0:
                slots.append((16, 'book'))
        elif kind == 'book':
            order, predictors = struct.unpack('>II', read(pos, 8))
            if not (1 <= order <= 8 and 1 <= predictors <= 8):
                raise ValueError('Invalid serialized predictor dimensions')
            length, slots = 8 + order * predictors * 16, []
        else:
            length, slots = {'envelope': 16, 'keymap': 8, 'adpcmloop': 44, 'rawloop': 12}[kind], []
        raw = read(pos, length)
        for slot, child in slots:
            pointer = u32(raw, slot)
            if pointer:
                visit(child, pointer)
            elif child in ('bank', 'sound', 'envelope', 'keymap', 'wave', 'book'):
                raise ValueError('Missing required serialized audio pointer')
    visit('file', 0)
    return {'sound_records': len(sounds), 'wave_records': len(waves)}


def main():
    ref = Reference()
    bank_base, sample_base = struct.unpack_from('>II', ref.rom, 0x3d750)
    bank = Bank(ref, bank_base, 0x8004d9f0, sample_base - bank_base, sample_base)
    if bank.record('file', 0) != 0:
        raise ValueError('Serialized audio bank header is not at offset zero')
    verified = verify_bank(bank.ctl, bank.tbl)
    for (offset, length), converted in bank.samples.items():
        if bank.tbl[converted:converted + length] != ref.rom[sample_base + offset:sample_base + offset + length]:
            raise ValueError('Sample payload changed during repacking')
    # FGM's RAM placement depends on the expanded music-table header size.
    music_base = u32(ref.rom, 0x3d768)
    music_count = struct.unpack_from('>H', ref.rom, music_base + 2)[0]
    difference = (((music_count + 1) * 8 + 15) & ~15) - 0x35c0
    tbl = package(ref, u32(ref.rom, 0x3d790), 0x80073f80 + difference, 0x2dd0,
                  'FGM.sfx_fgm_table_extended', 'FGM.fgm_microcode_extended')
    ucd = package(ref, u32(ref.rom, 0x3d798), 0x80076d50 + difference, 0x4b20,
                  'FGM.fgm_microcode_extended', 'FGM.extended_voice_map_table')
    out = BUILD / 'audio'
    out.mkdir(exist_ok=True)
    files = {'B1_sounds2_ctl.bin': bank.ctl, 'B1_sounds2_tbl.bin': bank.tbl,
             'fgm_tbl.bin': tbl, 'fgm_ucd.bin': ucd}
    for name, data in files.items():
        (out / name).write_bytes(data)
    report = {'source_rom_sha256': sha256(ref.path), 'sound_records': sum(k[0] == 'sound' for k in bank.cache),
              'samples': len(bank.samples), 'fgm_table_count': u32(tbl), 'fgm_microcode_count': u32(ucd),
              'serialized_bank_verified': verified, 'sample_payloads_verified': len(bank.samples),
              'files': {n: {'bytes': len(v), 'sha256': sha256(out/n)} for n, v in files.items()}}
    write_json(out / 'manifest.json', report)
    print(report)


if __name__ == '__main__':
    main()
