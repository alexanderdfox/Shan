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

def fib(n):
        if n <= 1:
            return n
        else:
            return fib(n - 1) + fib(n - 2)

"""Generated from Shàn — Fibonacci"""
_env: dict = {}

def _main():
    # rib: default
    _env['fib'] = fib
    for i in range(10):
        _env['f'] = _env['fib'](i)
        print(_env['f'])

if __name__ == "__main__":
    _main()
