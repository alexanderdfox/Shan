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

"""Generated from Shàn — Hello"""
_env: dict = {}

def _main():
    # rib: default
    print('Hello from Shàn')
    _env['x'] = 2 + 3
    print(_env['x'])

if __name__ == "__main__":
    _main()
