from typing import Any, Dict, List, Union

def _php_str(s: str) -> str:
    b = s.encode("utf-8")
    return f's:{len(b)}:"{b.decode("utf-8")}";'

def _php_int(i: int) -> str:
    return f"i:{i};"

def _php_float(d: float) -> str:
    if float(d).is_integer():
        return f"d:{int(d)};"
    return f"d:{float(d)};"

def _php_bool(b: bool) -> str:
    return f"b:{1 if b else 0};"

def _php_null() -> str:
    return "N;"

def _php_key(k: Union[int, str]) -> str:
    if isinstance(k, int):
        return _php_int(k)
    return _php_str(str(k))

def _php_val(v: Any) -> str:
    if v is None:
        return _php_null()
    if isinstance(v, bool):
        return _php_bool(v)
    if isinstance(v, int):
        return _php_int(v)
    if isinstance(v, float):
        return _php_float(v)
    if isinstance(v, str):
        return _php_str(v)
    if isinstance(v, list):
        return _php_array(v)
    if isinstance(v, dict):
        return _php_array(v)
    raise TypeError(f"Unsupported value type: {type(v)}")

def _php_array(obj: Union[List[Any], Dict[Any, Any]]) -> str:
    items: List[str] = []
    if isinstance(obj, list):
        for i, v in enumerate(obj):
            items.append(_php_key(i) + _php_val(v))
        return f"a:{len(obj)}:{{{''.join(items)}}}"
    elif isinstance(obj, dict):
        for k, v in obj.items():
            items.append(_php_key(k) + _php_val(v))
        return f"a:{len(obj)}:{{{''.join(items)}}}"
    else:
        raise TypeError("php_array expects list or dict")
