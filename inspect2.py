import sys
import fitdecode

path = sys.argv[1]
want = set(sys.argv[2].split(",")) if len(sys.argv) > 2 else set()
order = []
compressed = 0
with fitdecode.FitReader(path) as fr:
    for frame in fr:
        if isinstance(frame, fitdecode.FitDataMessage):
            if getattr(frame, "time_offset", None) is not None:
                compressed += 1
            order.append(frame.name)
            if frame.name in want:
                print(frame.name, "local", frame.local_mesg_num)
                for f in frame.fields:
                    print(f"   {f.def_num if f.field_def else '-':>4} {f.name:40} {f.value!r:.120} "
                          f"{'' if not f.field_def else f.field_def.base_type.name}{'[%d]' % f.field_def.size if f.field_def else ''}")
                for f in (frame.dev_fields if hasattr(frame, 'dev_fields') else []):
                    print("   DEV", f)
print("compressed:", compressed)
print("HEAD", order[:60])
print("TAIL", order[-40:])
