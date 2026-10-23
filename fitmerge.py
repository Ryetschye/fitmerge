"""Merge two consecutive Garmin FIT activities into one activity (one session, one lap per part).

Works on the raw FIT record stream: every message of both files is copied byte for byte and only
the summary messages (activity, session, lap, split, split_summary, time_in_zone and the
proprietary physiological summary 140) are rewritten. Built for the summary-first layout of the
Edge 1050, where the summary block precedes the first timestamp_correlation message.
"""
import argparse
import struct

CRC_TABLE = (0x0000, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401,
             0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400)

# base type -> (struct format, size, invalid value; None = all bytes 0xFF)
BASE = {
    0x00: ("B", 1, 0xFF), 0x01: ("b", 1, 0x7F), 0x02: ("B", 1, 0xFF),
    0x83: ("h", 2, 0x7FFF), 0x84: ("H", 2, 0xFFFF), 0x85: ("i", 4, 0x7FFFFFFF),
    0x86: ("I", 4, 0xFFFFFFFF), 0x88: ("f", 4, None), 0x89: ("d", 8, None),
    0x0A: ("B", 1, 0x00), 0x8B: ("H", 2, 0x0000), 0x8C: ("I", 4, 0x00000000), 0x0D: ("B", 1, 0xFF),
    0x8E: ("q", 8, 0x7FFFFFFFFFFFFFFF), 0x8F: ("Q", 8, 0xFFFFFFFFFFFFFFFF), 0x90: ("Q", 8, 0),
}

DEVICE_SETTINGS, USER_PROFILE, ZONES_TARGET, SPORT, TRAINING_SETTINGS = 2, 3, 7, 12, 13
SESSION, LAP, RECORD, EVENT, ACTIVITY = 18, 19, 20, 21, 34
UNKNOWN_22, UNKNOWN_79, PHYSIO_SUMMARY = 22, 79, 140
TIMESTAMP_CORRELATION, FIELD_DESCRIPTION, DEVELOPER_DATA_ID = 162, 206, 207
TIME_IN_ZONE, SPLIT, SPLIT_SUMMARY = 216, 312, 313
UNKNOWN_526, UNKNOWN_545 = 526, 545
EVENT_RECOVERY_HR = 21
RECORD_RUNNING_TOTALS = (5, 29)  # distance, accumulated_power: part 2 continues from the end of part 1

# Per-activity settings that the Edge writes once near the start of the record stream.
SETTINGS = {141, 394, DEVICE_SETTINGS, USER_PROFILE, 147, SPORT, TRAINING_SETTINGS, ZONES_TARGET}

DEV = "dev"
SESSION_RULES = {
    "sum": {8, 9, 10, 11, 13, 22, 23, 48, 94, 112, 113, 138, 168, 178, 188, 196, 202},
    "max": {15, 17, 19, 21, 24, 29, 30, 58, 93, 121, 123, 125, 137, 170, (DEV, 0, 6)},
    "min": {31, 32, 64, 150, 180, (DEV, 0, 7)},
    "wavg": {16, 18, 20, 57, 92, 101, 102, 103, 104, 105, 114, 115, 120, 122, 139, 169,
             205, 206, 207, (DEV, 0, 5)},
    "circ": {116, 117, 118, 119},
    "lr": {37},
    "last": {38, 39},
}
SPLIT_SUMMARY_RULES = {
    "sum": {3, 4, 5, 8, 9, 13, 16, 29, 56, 58, 59, 64, 65, 77},
    "max": {7, 11, 15, 18, 26, 37, 53, 60, 101},
    "min": {19, 79, 87},
    "wavg": {10, 12, 14, 17, 25, 30, 31, 36, 38, 39, 40, 41, 42, 72},
    "mean": {52},
    "circ": {32, 33, 34, 35},
    "lr": {28},
}


def crc16(data, crc=0):
    for byte in data:
        tmp = CRC_TABLE[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc ^= tmp ^ CRC_TABLE[byte & 0xF]
        tmp = CRC_TABLE[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc ^= tmp ^ CRC_TABLE[(byte >> 4) & 0xF]
    return crc


class Definition:
    def __init__(self, arch, gnum, fields, dev_fields):
        self.gnum = gnum
        self.fields = fields          # [(field_num, size, base_type)]
        self.dev_fields = dev_fields  # [(field_num, size, developer_data_index)]
        self.endian = ">" if arch else "<"
        self.size = sum(f[1] for f in fields) + sum(d[1] for d in dev_fields)
        body = bytes([0, arch]) + struct.pack(self.endian + "H", gnum) + bytes([len(fields)])
        body += b"".join(bytes(f) for f in fields)
        if dev_fields:
            body += bytes([len(dev_fields)]) + b"".join(bytes(d) for d in dev_fields)
        self.key = body

    def encode(self, local):
        return bytes([0x40 | (0x20 if self.dev_fields else 0) | local]) + self.key


class Message:
    def __init__(self, defn, data, dev_types):
        self.defn = defn
        self.dev_types = dev_types
        self.raw = {}
        pos = 0
        for num, size, _ in defn.fields:
            self.raw[num] = data[pos:pos + size]
            pos += size
        for num, size, idx in defn.dev_fields:
            self.raw[(DEV, idx, num)] = data[pos:pos + size]
            pos += size

    @property
    def num(self):
        return self.defn.gnum

    def copy(self):
        m = Message.__new__(Message)
        m.defn, m.dev_types, m.raw = self.defn, self.dev_types, dict(self.raw)
        return m

    def _base(self, key):
        if isinstance(key, tuple):
            return self.dev_types[(key[1], key[2])]
        return next(base for num, _, base in self.defn.fields if num == key)

    def get(self, key):
        raw = self.raw.get(key)
        if raw is None or self._base(key) not in BASE:
            return raw
        fmt, size, invalid = BASE[self._base(key)]
        n = len(raw) // size
        vals = struct.unpack(self.defn.endian + fmt * n, raw[:n * size])
        out = [None if (raw[i * size:(i + 1) * size] == b"\xff" * size if invalid is None else v == invalid)
               else v for i, v in enumerate(vals)]
        if n == 1:
            return out[0]
        return tuple(out) if any(v is not None for v in out) else None

    def set(self, key, value):
        fmt, size, invalid = BASE[self._base(key)]
        n = len(self.raw[key]) // size
        vals = value if isinstance(value, tuple) else (value,) * n if value is None else (value,)
        if len(vals) != n:
            raise ValueError(f"field {key}: expected {n} values, got {len(vals)}")
        parts = []
        for v in vals:
            if v is None:
                parts.append(b"\xff" * size if invalid is None else struct.pack(self.defn.endian + fmt, invalid))
            else:
                parts.append(struct.pack(self.defn.endian + fmt, v if invalid is None else int(round(v))))
        self.raw[key] = b"".join(parts)

    def encode(self, local):
        keys = [num for num, _, _ in self.defn.fields] + [(DEV, idx, num) for num, _, idx in self.defn.dev_fields]
        return bytes([local]) + b"".join(self.raw[k] for k in keys)


def read_fit(path):
    with open(path, "rb") as fh:
        data = fh.read()
    hsize = data[0]
    end = hsize + struct.unpack("<I", data[4:8])[0]
    if data[8:12] != b".FIT":
        raise ValueError(f"{path}: not a FIT file")
    if crc16(data[:end]) != struct.unpack("<H", data[end:end + 2])[0]:
        raise ValueError(f"{path}: file CRC mismatch")
    pos, defs, dev_types, msgs = hsize, {}, {}, []
    while pos < end:
        header = data[pos]
        pos += 1
        if header & 0x80:
            raise ValueError(f"{path}: compressed timestamp headers are not supported")
        local = header & 0x0F
        if header & 0x40:
            arch = data[pos + 1]
            gnum = struct.unpack((">" if arch else "<") + "H", data[pos + 2:pos + 4])[0]
            nf = data[pos + 4]
            pos += 5
            fields = [tuple(data[pos + 3 * i:pos + 3 * i + 3]) for i in range(nf)]
            pos += 3 * nf
            dev_fields = []
            if header & 0x20:
                nd = data[pos]
                pos += 1
                dev_fields = [tuple(data[pos + 3 * i:pos + 3 * i + 3]) for i in range(nd)]
                pos += 3 * nd
            defs[local] = Definition(arch, gnum, fields, dev_fields)
        else:
            defn = defs[local]
            msg = Message(defn, data[pos:pos + defn.size], dev_types)
            pos += defn.size
            if msg.num == FIELD_DESCRIPTION:
                dev_types[(msg.get(0), msg.get(1))] = msg.get(2)
            msgs.append(msg)
    return data[:hsize], msgs


class Writer:
    def __init__(self):
        self.body = bytearray()
        self.slots = {}           # local -> definition key
        self.lru = list(range(16))

    def write(self, msg):
        key = msg.defn.key
        local = next((loc for loc, k in self.slots.items() if k == key), None)
        if local is None:
            local = self.lru[0]
            self.slots[local] = key
            self.body += msg.defn.encode(local)
        self.lru.remove(local)
        self.lru.append(local)
        self.body += msg.encode(local)

    def file_bytes(self, template_header):
        hdr = bytes([14, template_header[1]]) + template_header[2:4] + struct.pack("<I", len(self.body)) + b".FIT"
        out = hdr + struct.pack("<H", crc16(hdr)) + bytes(self.body)
        return out + struct.pack("<H", crc16(out))


def combine(fn, a, b):
    if a is None:
        return b
    if b is None:
        return a
    if isinstance(a, tuple):
        return tuple(combine(fn, x, y) for x, y in zip(a, b))
    return fn(a, b)


def merge_fields(a, b, rules, wa, wb):
    """Return a copy of message a with every rule-covered field combined with message b."""
    def wavg(x, y):
        return x if wa + wb == 0 else (x * wa + y * wb) / (wa + wb)

    def circ(x, y):  # angles as uint8, 256 units per turn
        if abs(x - y) > 128:
            x, y = (x + 256, y) if x < y else (x, y + 256)
        return int(round(wavg(x, y))) % 256

    def lr(x, y):  # bit 15 = value refers to the right side, low 14 bits = percent * 100
        side, xv, yv = x & 0x8000, x & 0x3FFF, y & 0x3FFF
        if (y & 0x8000) != side:
            yv = 10000 - yv
        return side | int(round(wavg(xv, yv)))

    fns = {"sum": lambda x, y: x + y, "max": max, "min": min, "wavg": wavg, "mean": lambda x, y: (x + y) / 2,
           "circ": circ, "lr": lr, "last": lambda x, y: y}
    m = a.copy()
    for rule, keys in rules.items():
        for key in keys & m.raw.keys():
            m.set(key, combine(fns[rule], a.get(key), b.get(key) if key in b.raw else None))
    return m


def only(msgs, num):
    found = [m for m in msgs if m.num == num]
    if len(found) != 1:
        raise ValueError(f"expected exactly one message {num}, found {len(found)}")
    return found[0]


def tiz_ref(m):
    return (m.get(0), m.get(1)) if m.num == TIME_IN_ZONE else None


def merge_session(a, b):
    ta, tb = a.get(8), b.get(8)
    m = merge_fields(a, b, SESSION_RULES, ta, tb)
    m.set(7, (b.get(2) - a.get(2)) * 1000 + b.get(7))   # elapsed: start of part 1 to end of part 2
    m.set(26, 2)                                         # num_laps
    if m.get(124) is not None:
        m.set(124, m.get(9) / 100 / (m.get(8) / 1000) * 1000)
    if 14 in m.raw and m.get(14) is not None:
        m.set(14, m.get(9) / 100 / (m.get(8) / 1000) * 1000)
    ftp = a.get(45)
    if None not in (ftp, a.get(34), b.get(34), a.get(35), b.get(35), a.get(36), b.get(36)):
        # Effective seconds behind each TSS value (TSS = t * IF^2 / 36), then NP over both parts.
        ea = a.get(35) / 10 * 36 / (a.get(36) / 1000) ** 2
        eb = b.get(35) / 10 * 36 / (b.get(36) / 1000) ** 2
        np_ = ((a.get(34) ** 4 * ea + b.get(34) ** 4 * eb) / (ea + eb)) ** 0.25
        m.set(34, np_)
        m.set(36, np_ / ftp * 1000)
        m.set(35, (ea + eb) * (np_ / ftp) ** 2 / 36 * 10)
    return m


def merge_split_summary(a, b):
    wa, wb = a.get(4) or 0, b.get(4) or 0
    m = merge_fields(a, b, SPLIT_SUMMARY_RULES, wa, wb)
    if m.get(6) is not None and m.get(4):
        m.set(6, m.get(5) / 100 / (m.get(4) / 1000) * 1000)
    if m.get(27) is not None and a.get(27) is not None and b.get(27) is not None and wa + wb:
        m.set(27, ((a.get(27) ** 4 * wa + b.get(27) ** 4 * wb) / (wa + wb)) ** 0.25)
    return m


def merge_summary(sa, sb):
    ses_a, ses_b = only(sa, SESSION), only(sb, SESSION)
    lap_a, lap_b = only(sa, LAP), only(sb, LAP)
    ta, tb = ses_a.get(8), ses_b.get(8)
    b_start = ses_b.get(2)
    n_split_a = sum(1 for m in sa if m.num == SPLIT)

    session = merge_session(ses_a, ses_b)

    activity = only(sa, ACTIVITY).copy()
    activity.set(0, only(sa, ACTIVITY).get(0) + only(sb, ACTIVITY).get(0))

    physio = only(sb, PHYSIO_SUMMARY).copy()   # latest physiological state, patched to both parts
    pa = only(sa, PHYSIO_SUMMARY)
    for key in (60, 61):                       # ascent, descent
        physio.set(key, combine(lambda x, y: x + y, pa.get(key), physio.get(key)))
    for key in (62, 63):                       # avg power, avg heart rate
        physio.set(key, combine(lambda x, y: (x * ta + y * tb) / (ta + tb), pa.get(key), physio.get(key)))

    lap1 = lap_b.copy()
    lap1.set(254, 1)
    lap1.set(253, lap_a.get(253))              # the Edge stamps every lap with the activity start
    lap1.set(7, session.get(7) - lap_a.get(7)) # the pause before a manual restart counts into the next lap
    lap1_tiz = next(m for m in sb if tiz_ref(m) == (LAP, 0)).copy()
    lap1_tiz.set(1, 1)
    lap1_tiz.set(253, lap_a.get(253))

    split_block_b = []
    for m in sb:
        if m.num == SPLIT:
            m = m.copy()
            m.set(254, m.get(254) + n_split_a)
            split_block_b.append(m)
        elif tiz_ref(m) is not None and tiz_ref(m)[0] == SPLIT:
            m = m.copy()
            m.set(1, m.get(1) + n_split_a)
            split_block_b.append(m)

    ss_b = {m.get(0): m for m in sb if m.num == SPLIT_SUMMARY}
    out = []
    for m in sa:
        if m.num == ACTIVITY:
            out.append(activity)
        elif m.num == PHYSIO_SUMMARY:
            out.append(physio)
        elif m.num == SESSION:
            out.append(session)
        elif tiz_ref(m) == (SESSION, 0):
            tiz = merge_fields(m, next(x for x in sb if tiz_ref(x) == (SESSION, 0)), {"sum": {2, 3, 4, 5}}, 0, 0)
            out.append(tiz)
        elif tiz_ref(m) == (LAP, 0):
            out += [m, lap1, lap1_tiz]
        elif m.num == SPLIT:
            start, elapsed = m.get(9), m.get(1)
            if start is not None and elapsed is not None and start * 1000 + elapsed > b_start * 1000:
                m = m.copy()                   # splits written while paused run into part 2 otherwise
                m.set(1, max(0, (b_start - start) * 1000))
            out.append(m)
        elif m.num == SPLIT_SUMMARY:
            if split_block_b:
                out += split_block_b
                split_block_b = []
            other = ss_b.pop(m.get(0), None)
            out.append(merge_split_summary(m, other) if other is not None else m)
        else:
            out.append(m)
    if ss_b:
        raise ValueError(f"split types only in second file: {sorted(ss_b)}")
    return out


def merge_streams(stream_a, stream_b):
    settings_b = [m for m in stream_b if m.num in SETTINGS]
    if any(m.num in SETTINGS for m in stream_a):
        settings_b = []
    known_a = {m.num for m in stream_a}
    fdesc_a = {tuple(sorted(m.raw.items(), key=str)) for m in stream_a if m.num == FIELD_DESCRIPTION}
    offsets = {key: next((m.get(key) for m in reversed(stream_a)
                          if m.num == RECORD and key in m.raw and m.get(key) is not None), None)
               for key in RECORD_RUNNING_TOTALS}

    out, inserted = [], not settings_b
    for m in stream_a:
        if m.num == UNKNOWN_526 or (m.num == EVENT and m.get(0) == EVENT_RECOVERY_HR):
            continue                           # end-of-activity markers; part 2 brings its own
        out.append(m)
        if not inserted and m.num == UNKNOWN_22:
            out += settings_b
            inserted = True
    if not inserted:
        out += settings_b
    for m in stream_b:
        if m.num in SETTINGS and settings_b:
            continue
        if m.num in (UNKNOWN_79, UNKNOWN_545) and m.num in known_a:
            continue
        if m.num == FIELD_DESCRIPTION and tuple(sorted(m.raw.items(), key=str)) in fdesc_a:
            continue
        if m.num == RECORD:
            m = m.copy()
            for key, offset in offsets.items():
                if offset is not None and key in m.raw and m.get(key) is not None:
                    m.set(key, m.get(key) + offset)
        out.append(m)
    return out


def split_blocks(msgs):
    i = next(i for i, m in enumerate(msgs) if m.num == TIMESTAMP_CORRELATION)
    return msgs[:i], msgs[i:]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("first")
    ap.add_argument("second")
    ap.add_argument("output")
    args = ap.parse_args()

    header_a, msgs_a = read_fit(args.first)
    _, msgs_b = read_fit(args.second)
    sum_a, stream_a = split_blocks(msgs_a)
    sum_b, stream_b = split_blocks(msgs_b)
    if only(sum_b, SESSION).get(2) <= only(sum_a, SESSION).get(2):
        raise ValueError("second file must start after the first one")

    writer = Writer()
    for m in merge_summary(sum_a, sum_b) + merge_streams(stream_a, stream_b):
        writer.write(m)
    with open(args.output, "wb") as fh:
        fh.write(writer.file_bytes(header_a))
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
