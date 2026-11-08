def parse_line(line, sep=","):
    fields, cur, quoted, i = [], [], False, 0
    while i < len(line):
        ch = line[i]
        if quoted:
            if ch == '"':
                if i + 1 < len(line) and line[i + 1] == '"':
                    cur.append('"')
                    i += 1
                else:
                    quoted = False
            else:
                cur.append(ch)
        elif ch == '"':
            quoted = True
        elif ch == sep:
            fields.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
        i += 1
    if quoted:
        raise ValueError("unterminated quote")
    fields.append("".join(cur))
    return fields
