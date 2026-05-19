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

"""Generated from Shàn — Secrets"""
_env: dict = {}

def _main():
    # rib: default
    with shan_open('keys', 'demo'):
        _env['apiKey'] = Span('sk_live_fan_demo', uses_left=2)
        _env['apiKey_observed'] = shan_observe(_env['apiKey'], 'first-read')
        print(_env['apiKey_observed'])
        with shan_open('keys', 'seal-data'):
            _env['sealed'] = shan_seal('payload', _env['apiKey_observed'])
            print(_env['sealed'])

if __name__ == "__main__":
    _main()
