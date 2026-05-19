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

"""Generated from Shàn — HalfLogic"""
_env: dict = {}

def _main():
    # rib: default
    _env['allowed'] = Half
    _half_key = match_half(_env.get('allowed', Half))
    if _half_key == 'half':
        print('Still deciding (½)')
    _env['allowed'] = Yes
    _half_key = match_half(_env.get('allowed', Half))
    if _half_key == 'yes':
        print('Allowed')
    elif _half_key == 'no':
        raise RuntimeError("access denied")

if __name__ == "__main__":
    _main()
