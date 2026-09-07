\
from pathlib import Path
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SRC = ROOT / "example_packages" / "hello_jns"
OUT = ROOT / "example_packages" / "jns_v4_2_test_package.zip"

with zipfile.ZipFile(OUT, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    for path in sorted(SRC.rglob("*")):
        if path.is_file():
            zf.write(path, path.relative_to(SRC).as_posix())

print(OUT)
