from pathlib import Path
import argparse, json, sys
from .parser import parse_file
from .runner import run_program

BANNER="""============================================================
 PISS v0.1 — Pressure-Informed Symbolic System
 WADRRB: WANT -> ACT -> DO -> RECKON -> REPAIR -> BURY
============================================================"""

def main(argv=None):
    ap=argparse.ArgumentParser(prog="piss")
    sub=ap.add_subparsers(dest="cmd",required=True)
    c=sub.add_parser("check"); c.add_argument("program")
    r=sub.add_parser("run"); r.add_argument("program"); r.add_argument("--receipts",default="receipts/piss")
    h=sub.add_parser("history"); h.add_argument("--receipts",default="receipts/piss")
    a=ap.parse_args(argv)
    try:
        if a.cmd=="check":
            ins=parse_file(a.program); print(BANNER); print(f"VALID: {a.program}")
            for x in ins: print(f"{x.line_no:>3}  {x.op:<7} {x.arg}")
            return 0
        if a.cmd=="run":
            print(BANNER); print(f"Running: {a.program}")
            status,receipt,steps=run_program(a.program,a.receipts)
            for s in steps:
                print(f"[{s['op']}] {s['arg']}")
                if 'error' in s: print('  ERROR: '+s['error'])
                else:
                    rr=s.get('result'); print('  '+(json.dumps(rr,ensure_ascii=False) if isinstance(rr,dict) else str(rr)))
            print(f"\nSTATUS: {status}\nRECEIPT: {receipt}")
            return 0 if status=="PASS" else 1
        if a.cmd=="history":
            files=sorted(Path(a.receipts).glob('*.json'),reverse=True)
            if not files: print('No PISS receipts yet.'); return 0
            for p in files:
                d=json.loads(p.read_text(encoding='utf-8')); print(f"{p.name}  {d.get('status')}  {d.get('goal')}")
            return 0
    except Exception as e:
        print(f"PISS ERROR: {type(e).__name__}: {e}",file=sys.stderr); return 2

if __name__=='__main__': raise SystemExit(main())
