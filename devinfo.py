import sys
import fitdecode

for path in sys.argv[1:]:
    print("=====", path.split("/")[-1])
    order = []
    compressed = 0
    with fitdecode.FitReader(path) as fr:
        for frame in fr:
            if isinstance(frame, fitdecode.FitDefinitionMessage) and frame.dev_field_defs:
                print("  DEFDEV", frame.name, [(d.dev_data_index, d.def_num, d.size) for d in frame.dev_field_defs])
            if not isinstance(frame, fitdecode.FitDataMessage):
                continue
            if getattr(frame, "time_offset", None) is not None:
                compressed += 1
            order.append(frame.name)
            if frame.name == "developer_data_id":
                print("  DEVID idx", frame.get_value("developer_data_index"), "app",
                      bytes(frame.get_value("application_id")).hex(), "ver", frame.get_value("application_version"))
            elif frame.name == "field_description":
                print("  FDESC idx", frame.get_value("developer_data_index"), "num",
                      frame.get_value("field_definition_number"), frame.get_value("field_name"),
                      frame.get_value("native_mesg_num"), frame.get_value("fit_base_type_id"))
    print("  compressed:", compressed)
    print("  TAIL", order[-30:])
