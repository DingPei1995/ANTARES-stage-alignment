import re
import h5py
import numpy as np

PAT = re.compile(r"(^|[/_.-])(st|sz|sn|srn|srz|ts|tz|tn|rz|rn|cps|cpx|cpz|cpt|cap|x|y|z|theta|phi|tilt|pos|position|value)$", re.I)
for name in ("Real_2026-11-14_18-08-53.nxs", "Real_2026-11-14_18-16-15.nxs"):
    print("==", name)
    with h5py.File(rf"D:\Codes\ANTARES-stage-alignment-main\Photos\{name}", "r") as f:
        def visit(path, obj):
            if isinstance(obj, h5py.Dataset) and obj.size <= 4 and obj.dtype.kind in "fiu":
                low = path.lower()
                if any(s in low for s in ("sample", "manip", "stage", "/st", "/sz", "/sn", "srn", "srz", "cps", "capil", "cx1", "tx", "ts", "rz")):
                    print(f"   {path} = {np.ravel(obj[()]).tolist()}")
        f.visititems(visit)
