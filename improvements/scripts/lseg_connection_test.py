"""LSEG connection test: open the Workspace desktop session and pull 5 daily closes for AAPL.O.
Reads the App Key from lseg-data.config.json (git-ignored). The key is never printed."""
import os, sys
from pathlib import Path
import lseg.data as ld

cands = [os.environ.get("LD_LIB_CONFIG_PATH", ""), str(Path.cwd() / "lseg-data.config.json"), str(Path.home() / "lseg-data.config.json")]
found = [c for c in cands if c and Path(c).is_file()]
print("config file found:", bool(found), "|", [Path(c).name + " in " + str(Path(c).parent) for c in found])
if not found:
    sys.exit("No lseg-data.config.json found (cwd, ~, or $LD_LIB_CONFIG_PATH). Create it with your App Key; see docs.")
session = None
try:
    session = ld.open_session()               # default session = desktop.workspace (http://localhost:9000)
    print("session state:", session.open_state)
    df = ld.get_history("AAPL.O", fields=["TRDPRC_1"], interval="daily", count=5)
    print(df)
finally:
    if session is not None:
        ld.close_session()
