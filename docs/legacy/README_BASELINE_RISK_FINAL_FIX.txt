BASELINE RISK FINAL FIX

What changed:
- Server forces LOW/NORMAL baseline whenever no attack scenario is active.
- Dashboard script cache version changed to baseline-contract-fix-v2.
- Client-side final guard sets rail Risk=Low and Threat=None whenever attack.active is false.

Run: stop old python process, then run python app.py from this folder.
In Chrome press Ctrl+Shift+R once after opening http://127.0.0.1:5000.
