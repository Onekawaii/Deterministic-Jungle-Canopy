from dataclasses import dataclass
from pathlib import Path

@dataclass
class Instruction:
    op: str
    arg: str
    line_no: int

VALID_OPS = {"WANT", "ACT", "DO", "RECKON", "REPAIR", "BURY"}

def parse_text(text: str):
    out=[]
    for i, raw in enumerate(text.splitlines(),1):
        line=raw.strip()
        if not line or line.startswith("#"):
            continue
        op,arg=(line.split(" ",1)+[""])[:2] if " " in line else (line,"")
        op=op.upper()
        if op not in VALID_OPS:
            raise ValueError(f"Line {i}: unknown PISS op {op!r}")
        out.append(Instruction(op,arg.strip(),i))
    if not out:
        raise ValueError("PISS program is empty.")
    if out[0].op != "WANT":
        raise ValueError("A PISS program must begin with WANT.")
    return out

def parse_file(path):
    return parse_text(Path(path).read_text(encoding="utf-8"))
