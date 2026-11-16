import json
from fractions import Fraction as F

def dumps(value):
    def convert(x):
        if isinstance(x, F):
            return str(x)
        if isinstance(x, dict):
            return {k: convert(v) for k, v in x.items()}
        if isinstance(x, (list, tuple)):
            return [convert(v) for v in x]
        return x
    return json.dumps(convert(value), sort_keys=True, separators=(",", ":"))

def dot(a, b):
    return sum((x*y for x, y in zip(a, b)), F(0))

def quadratic(w, cov):
    return sum((w[i]*cov[i][j]*w[j] for i in range(len(w))
                for j in range(len(w))), F(0))
