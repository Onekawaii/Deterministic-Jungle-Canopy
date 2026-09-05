from pathlib import Path
import os, platform, subprocess
from .parser import parse_file
from .receipts import write_receipt

def _run_shell(command):
    c=subprocess.run(command,shell=True,text=True,capture_output=True,timeout=30)
    return {"command":command,"returncode":c.returncode,"stdout":c.stdout.rstrip(),"stderr":c.stderr.rstrip()}

def run_program(program_path, receipt_dir="receipts/piss"):
    instructions=parse_file(program_path)
    goal=instructions[0].arg
    context={}; steps=[]; status="PASS"
    for ins in instructions:
        e={"op":ins.op,"arg":ins.arg,"line":ins.line_no}
        try:
            if ins.op=="WANT": e["result"]=f"Goal registered: {ins.arg}"
            elif ins.op=="ACT":
                t=ins.arg.lower()
                if t=="cwd": v=str(Path.cwd())
                elif t=="python":
                    import sys; v=sys.version.split()[0]
                elif t=="platform": v=platform.platform()
                elif t.startswith("env "): v=os.environ.get(ins.arg[4:].strip())
                else: v=f"unknown ACT target: {ins.arg}"
                context[ins.arg]=v; e["result"]=v
            elif ins.op=="DO":
                r=_run_shell(ins.arg); context["last_do"]=r; e["result"]=r
                if r["returncode"]!=0: status="FAIL"
            elif ins.op=="RECKON":
                check=ins.arg.lower(); last=context.get("last_do")
                if check=="last_do_passed": ok=bool(last) and last["returncode"]==0
                elif check=="last_do_failed": ok=bool(last) and last["returncode"]!=0
                elif check.startswith("file_exists "): ok=Path(ins.arg[len("file_exists "):].strip()).exists()
                elif check.startswith("contains "):
                    needle=ins.arg[len("contains "):]; ok=needle in ((last or {}).get("stdout", ""))
                else: raise ValueError(f"Unknown RECKON check: {ins.arg}")
                e["result"]={"passed":ok}
                if not ok: status="FAIL"
            elif ins.op=="REPAIR": e["result"]={"requested":ins.arg,"automatic":False,"note":"v0.1 records repairs; it does not mutate files automatically."}
            elif ins.op=="BURY": e["result"]="Receipt requested"
        except Exception as ex:
            status="FAIL"; e["error"]=f"{type(ex).__name__}: {ex}"
        steps.append(e)
    receipt=write_receipt(program_path,goal,steps,status,receipt_dir)
    return status,receipt,steps
