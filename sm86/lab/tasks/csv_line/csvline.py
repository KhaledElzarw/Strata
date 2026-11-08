def parse_line(line, sep=","):
    """Split one CSV line into fields.

    Fields are separated by `sep`. A field may be wrapped in double quotes; inside quotes `sep` is an ordinary
    character and two double quotes ("") stand for one. Whitespace is kept exactly as written. An empty line is one
    empty field. A quote that is never closed raises ValueError.
    """
    fields = []
    cur = ""
    quoted = False
    for ch in line:
        if quoted:
            if ch == '"':
                quoted = False
            else:
                cur += ch
        elif ch == '"':
            quoted = True
        elif ch == sep:
            fields.append(cur.strip())
            cur = ""
        else:
            cur += ch
    fields.append(cur.strip())
    return fields
