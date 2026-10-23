import sys
from collections import Counter

import fitdecode
from garmin_fit_sdk import Decoder, Stream

part_a, part_b, *cands = sys.argv[1:]

SKEYS = ["start_time", "total_elapsed_time", "total_timer_time", "total_distance", "total_ascent", "total_descent",
         "total_calories", "avg_heart_rate", "max_heart_rate", "avg_power", "max_power", "normalized_power",
         "training_stress_score", "intensity_factor", "total_training_effect", "training_load_peak",
         "enhanced_avg_speed", "enhanced_max_speed", "avg_cadence", "num_laps", "sport", "sub_sport",
         "sport_profile_name", "lap_trigger", "message_index"]


def load(path):
    counts, records, msgs, devrec = Counter(), [], {}, 0
    with fitdecode.FitReader(path, check_crc=fitdecode.CrcCheck.RAISE) as fr:
        for frame in fr:
            if isinstance(frame, fitdecode.FitHeader):
                hdr = (frame.header_size, frame.proto_ver, frame.profile_ver)
            if not isinstance(frame, fitdecode.FitDataMessage):
                continue
            counts[frame.name] += 1
            msgs.setdefault(frame.name, []).append(frame)
            if frame.name == "record":
                d = {f.name: f.value for f in frame.fields if f.value is not None}
                records.append(d)
                if any(getattr(f, "dev_field_def", None) for f in frame.fields if f.field_def is None):
                    devrec += 1
    return hdr, counts, records, msgs, devrec


def short(v):
    if hasattr(v, "strftime"):
        return v.strftime("%H:%M:%S")
    if isinstance(v, float):
        return round(v, 3)
    return v


_, ca, ra, _, _ = load(part_a)
_, cb, rb, _, _ = load(part_b)
orig = ra + rb
for path in cands:
    print("=" * 100)
    print(path)
    sdk = Decoder(Stream.from_file(path))
    print("sdk integrity:", sdk.check_integrity(), "errors:", Decoder(Stream.from_file(path)).read()[1])
    hdr, cm, rm, msgs, devrec = load(path)
    print("header:", hdr, "| records:", len(rm), "| records with developer fields:", devrec)
    print("file_id:", {f.name: short(f.value) for f in msgs["file_id"][0].fields if f.value is not None})
    print("message types:", dict(sorted(cm.items())))
    lost = sorted(n for n in set(ca) | set(cb) if n not in cm)
    print("message types from originals missing:", lost)
    for name in ("activity", "session", "lap"):
        for m in msgs.get(name, []):
            d = {k: short(m.get_value(k, fallback=None)) for k in SKEYS if m.get_value(k, fallback=None) is not None}
            print(f"  {name}: {d}")
    # record-level comparison by timestamp
    by_ts = {r["timestamp"]: r for r in rm}
    missing = [r["timestamp"] for r in orig if r["timestamp"] not in by_ts]
    extra = len(rm) - (len(orig) - len(missing))
    diff = Counter()
    lostf = Counter()
    for r in orig:
        n = by_ts.get(r["timestamp"])
        if n is None:
            continue
        for k, v in r.items():
            if k not in n:
                lostf[k] += 1
            elif n[k] != v and not (isinstance(v, float) and abs(n[k] - v) < 1e-3):
                diff[k] += 1
    print(f"  records missing vs originals: {len(missing)}, extra: {extra}")
    print("  record fields dropped (count of records):", dict(lostf.most_common(40)))
    print("  record fields changed (count of records):", dict(diff.most_common(40)))
