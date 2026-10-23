import sys
import fitdecode

KEYS = ["timestamp", "start_time", "total_elapsed_time", "total_timer_time", "total_distance", "message_index",
        "first_lap_index", "num_laps", "lap_trigger", "event", "event_type", "num_sessions", "type",
        "total_ascent", "total_descent", "total_calories", "avg_power", "normalized_power", "avg_heart_rate",
        "max_heart_rate", "enhanced_avg_speed", "enhanced_max_speed", "total_moving_time", "sport", "sub_sport",
        "split_type", "num_splits", "reference_mesg", "reference_index", "local_timestamp", "device_index",
        "data", "timer_trigger", "event_group"]


def fmt(v):
    if hasattr(v, "strftime"):
        return v.strftime("%H:%M:%S")
    return v


with fitdecode.FitReader(sys.argv[1]) as fr:
    for frame in fr:
        if not isinstance(frame, fitdecode.FitDataMessage):
            continue
        if frame.name in ("activity", "session", "lap", "event", "split", "split_summary", "time_in_zone",
                          "timestamp_correlation", "unknown_288", "unknown_326", "unknown_327"):
            d = {}
            for f in frame.fields:
                if f.value is None:
                    continue
                if f.name in KEYS or (frame.name.startswith("unknown") and f.name in ("timestamp", "253")):
                    d[f.name] = fmt(f.value)
            print(frame.name, d)
