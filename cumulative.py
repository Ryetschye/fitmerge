import sys
import fitdecode


def records(path, name="record"):
    out = []
    with fitdecode.FitReader(path) as fr:
        for frame in fr:
            if isinstance(frame, fitdecode.FitDataMessage) and frame.name == name:
                out.append({f.name: f.value for f in frame.fields if f.value is not None})
    return out


a, b, merged, fixed = sys.argv[1:5]
for name in ("record", "unknown_534"):
    ra, rb = records(a, name), records(b, name)
    print(f"== {name}: fields that never decrease in A and B (candidates for running totals)")
    for k in sorted(set(ra[0]) | set(rb[0])):
        va = [r[k] for r in ra if isinstance(r.get(k), (int, float)) and not isinstance(r.get(k), bool)]
        vb = [r[k] for r in rb if isinstance(r.get(k), (int, float)) and not isinstance(r.get(k), bool)]
        if len(va) < 10 or len(vb) < 10 or k == "timestamp":
            continue
        mono = all(x <= y for x, y in zip(va, va[1:])) and all(x <= y for x, y in zip(vb, vb[1:]))
        if mono and va[-1] > va[0]:
            print(f"   {k:28} A {va[0]} -> {va[-1]}   B {vb[0]} -> {vb[-1]}")

rm, rf = records(merged), records(fixed)
print("== distance around the join")
for label, rs in (("merged", rm), ("fixed", rf)):
    idx = next(i for i, r in enumerate(rs) if r["timestamp"].hour == 17)
    print(f"   {label:6}", [(r["timestamp"].strftime("%H:%M:%S"), r.get("distance")) for r in rs[idx - 2: idx + 2]],
          "last", rs[-1].get("distance"))
ts_f = {r["timestamp"] for r in rf}
print("== record missing in fixed:", [r["timestamp"] for r in rm if r["timestamp"] not in ts_f])
by = {r["timestamp"]: r for r in rf}
d = [abs(by[r["timestamp"]]["enhanced_speed"] - r["enhanced_speed"]) for r in rm
     if r["timestamp"] in by and "enhanced_speed" in r and "enhanced_speed" in by[r["timestamp"]]]
d.sort()
print(f"== speed change fixed vs original (m/s): median {d[len(d) // 2]:.3f}, p90 {d[int(len(d) * .9)]:.3f}, max {d[-1]:.3f}")
dev = [k for k in rm[100] if "temperature" in k.lower() or "ruuvi" in k.lower() or "core" in k.lower()]
print("== dev fields merged:", dev, "| fixed:", [k for k in rf[100] if k in dev])
