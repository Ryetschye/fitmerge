import sys
from collections import Counter

import fitdecode
from garmin_fit_sdk import Decoder, Stream

merged, part_a, part_b = sys.argv[1:4]

# 1) official Garmin FIT SDK
stream = Stream.from_file(merged)
dec = Decoder(stream)
print("sdk is_fit:", dec.is_fit(), "integrity:", dec.check_integrity())
messages, errors = Decoder(Stream.from_file(merged)).read(convert_datetimes_to_dates=True)
print("sdk errors:", errors)
print("sdk sessions:", len(messages["session_mesgs"]), "laps:", len(messages["lap_mesgs"]),
      "records:", len(messages["record_mesgs"]), "activity:", len(messages["activity_mesgs"]))


# 2) fitdecode with strict CRC, message counts and record payload comparison
def load(path):
    counts, records = Counter(), []
    with fitdecode.FitReader(path, check_crc=fitdecode.CrcCheck.RAISE) as fr:
        for frame in fr:
            if isinstance(frame, fitdecode.FitDataMessage):
                counts[frame.name] += 1
                if frame.name == "record":
                    records.append(tuple((f.name, f.value) for f in frame.fields))
    return counts, records


RUNNING = ("distance", "accumulated_power")


def strip(recs):
    return [tuple(kv for kv in r if kv[0] not in RUNNING) for r in recs]


cm, rm = load(merged)
ca, ra = load(part_a)
cb, rb = load(part_b)
print("records identical to A+B (running totals excluded):", strip(rm) == strip(ra + rb),
      len(rm), "=", len(ra), "+", len(rb))
ts = [dict(r)["timestamp"] for r in rm]
print("record timestamps strictly increasing:", all(x < y for x, y in zip(ts, ts[1:])), ts[0], "->", ts[-1])

# regression: running totals continue across the join instead of restarting at zero
ok = True
for key in RUNNING:
    vals = [dict(r)[key] for r in rm if dict(r).get(key) is not None]
    end_a = [dict(r)[key] for r in ra if dict(r).get(key) is not None][-1]
    shifted = [dict(r)[key] for r in rm[len(ra):] if dict(r).get(key) is not None]
    expect = [dict(r)[key] + end_a for r in rb if dict(r).get(key) is not None]
    mono = all(x <= y for x, y in zip(vals, vals[1:]))
    cont = all(abs(x - y) < 0.011 for x, y in zip(shifted, expect)) and len(shifted) == len(expect)
    print(f"{key}: never decreases {mono}, part 2 offset by end of part 1 ({end_a}) {cont}")
    ok &= mono and cont
session_distance = messages["session_mesgs"][0]["total_distance"]
last_distance = [dict(r)["distance"] for r in rm if dict(r).get("distance") is not None][-1]
print(f"last record distance {last_distance} == session total_distance {session_distance}:",
      abs(last_distance - session_distance) < 1)
ok &= abs(last_distance - session_distance) < 1
print("REGRESSION", "PASS" if ok else "FAIL")
print(f"{'message':24} {'A':>6} {'B':>6} {'A+B':>6} {'merged':>6}")
for name in sorted(set(ca) | set(cb) | set(cm)):
    if ca[name] + cb[name] != cm[name]:
        print(f"{name:24} {ca[name]:6} {cb[name]:6} {ca[name] + cb[name]:6} {cm[name]:6}")
