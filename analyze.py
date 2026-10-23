import sys
from collections import Counter, OrderedDict
import fitdecode

SHOW = {"file_id", "file_creator", "session", "lap", "activity", "event", "sport", "device_info",
        "training_file", "user_profile", "zones_target", "device_settings", "time_in_zone", "split",
        "split_summary", "workout", "hrv"}


def main(path, full=False):
    order = []
    counts = Counter()
    first_rec = last_rec = None
    dev = False
    with fitdecode.FitReader(path, check_crc=fitdecode.CrcCheck.RAISE) as fr:
        for frame in fr:
            if isinstance(frame, fitdecode.FitHeader):
                print("HEADER", frame.header_size, frame.proto_ver, frame.profile_ver, frame.body_size)
            if isinstance(frame, fitdecode.FitDefinitionMessage) and frame.dev_field_defs:
                dev = True
            if not isinstance(frame, fitdecode.FitDataMessage):
                continue
            n = frame.name
            counts[n] += 1
            if not order or order[-1][0] != n:
                order.append([n, 1])
            else:
                order[-1][1] += 1
            if n == "record":
                ts = frame.get_value("timestamp", fallback=None)
                if first_rec is None:
                    first_rec = ts
                last_rec = ts
            if n in SHOW and (full or n not in ("event", "device_info", "hrv")):
                vals = OrderedDict((f.name, f.value) for f in frame.fields if f.value is not None)
                print(f"--- {n}: {dict(vals)}")
            elif n in ("event",):
                vals = {f.name: f.value for f in frame.fields if f.value is not None}
                print(f"--- event: {vals}")
    print("COUNTS", dict(counts))
    print("RECORDS", first_rec, "->", last_rec, "dev_fields:", dev)
    print("ORDER", " ".join(f"{n}x{c}" for n, c in order))


if __name__ == "__main__":
    main(sys.argv[1], full="--full" in sys.argv)
