import json


def _same(x, y):
    return type(x) is type(y) and x == y


def diff(a, b):
    out = []

    def dump(v):
        return json.dumps(v, sort_keys=True)

    def walk(p, x, y):
        if isinstance(x, dict) and isinstance(y, dict):
            for k in x.keys() | y.keys():
                q = "%s.%s" % (p, k)
                if k not in y:
                    out.append("- %s: %s" % (q, dump(x[k])))
                elif k not in x:
                    out.append("+ %s: %s" % (q, dump(y[k])))
                else:
                    walk(q, x[k], y[k])
        elif isinstance(x, list) and isinstance(y, list):
            for i in range(max(len(x), len(y))):
                q = "%s[%d]" % (p, i)
                if i >= len(y):
                    out.append("- %s: %s" % (q, dump(x[i])))
                elif i >= len(x):
                    out.append("+ %s: %s" % (q, dump(y[i])))
                else:
                    walk(q, x[i], y[i])
        elif not _same(x, y):
            out.append("~ %s: %s -> %s" % (p, dump(x), dump(y)))

    walk("$", a, b)
    return sorted(out)
