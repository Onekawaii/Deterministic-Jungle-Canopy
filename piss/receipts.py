from pathlib import Path
from datetime import datetime, timezone
import json, hashlib

def write_receipt(program_path, goal, steps, status, out_dir="receipts/piss"):
    out=Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    now=datetime.now(timezone.utc)
    payload={"piss_version":"0.1.0","grammar":"WADRRB","timestamp_utc":now.isoformat(),"program":str(program_path),"goal":goal,"status":status,"steps":steps}
    canonical=json.dumps(payload,sort_keys=True,separators=(",",":"))
    payload["receipt_sha256"]=hashlib.sha256(canonical.encode()).hexdigest()
    path=out/f"{now.strftime('%Y%m%dT%H%M%SZ')}_{status.lower()}.json"
    path.write_text(json.dumps(payload,indent=2),encoding="utf-8")
    return path
