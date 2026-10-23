import sys
import fitdecode


def first(path, name, idx=0):
    n = 0
    with fitdecode.FitReader(path) as fr:
        for frame in fr:
            if isinstance(frame, fitdecode.FitDataMessage) and frame.name == name:
                if n == idx:
                    return frame
                n += 1


name = sys.argv[1]
a = first(sys.argv[2], name)
b = first(sys.argv[3], name)
r = first(sys.argv[4], name)


def table(m):
    return {(f.def_num if f.field_def else ("dev", f.dev_field_def.dev_data_index, f.dev_field_def.def_num) if getattr(f, "dev_field_def", None) else f.name): f for f in m.fields}


ta, tb, tr = table(a), table(b), table(r)
for k in ta:
    fa, fb, fr_ = ta[k], tb.get(k), tr.get(k)
    def v(f):
        if f is None:
            return "--"
        x = f.value
        if isinstance(x, tuple):
            x = tuple(round(i, 1) if isinstance(i, float) else i for i in x)
        elif isinstance(x, float):
            x = round(x, 3)
        return str(x)[:40]
    print(f"{str(k):>14} {fa.name[:34]:34} {v(fa):>40} {v(fb):>40} | ref {v(fr_)}")
extra = [k for k in tb if k not in ta]
print("only in B:", extra)
