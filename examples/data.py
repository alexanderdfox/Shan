from shan.compiled_support import *

import json as _json
import math as _math

def json_dumps(o):
    return _json.dumps(o)

def json_loads(s):
    return _json.loads(s)

def sqrt(x):
    return _math.sqrt(x)

def sin(x):
    return _math.sin(x)

def cos(x):
    return _math.cos(x)

def tan(x):
    return _math.tan(x)

def log(x):
    return _math.log(x)

pi = _math.pi

"""Generated from Shàn — Data"""
_env: dict = {}

def _main():
    # rib: default
    _env['xs'] = [1, 2, 3, 4, 5]
    _env['doubled'] = [x * 2 for x in _env['xs']]
    print(_env['doubled'])
    _env['d'] = {'name': 'Shàn', 'version': 1}
    print(json_dumps(_env['d']))
    import math as math
    _env['math'] = math
    print(sqrt(144))

if __name__ == "__main__":
    _main()
