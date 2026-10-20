import json
import sys
import time


def log(event: str, /, **fields: object) -> None:
    print(json.dumps({"t": round(time.time(), 3), **fields, "event": event}, ensure_ascii=False), file=sys.stdout, flush=True)
