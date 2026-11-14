r"""Oyuncu .dat dosyasının yapısını yazdırır (teşhis için).
Kullanım:  uv run --with nbtlib python nbt_dok.py "C:\...\world\playerdata\<uuid>.dat"
Çıktı aynı klasöre nbt_dok.txt olarak da kaydedilir."""
import sys
from core.players import read_nbt


def dump(tag, indent=0, out=None, max_list=6):
    pad = "  " * indent
    if hasattr(tag, "keys"):
        for k in tag.keys():
            v = tag[k]
            if hasattr(v, "keys") or isinstance(v, list):
                n = f" [{len(v)}]" if isinstance(v, list) else ""
                out.append(f"{pad}{k} ({type(v).__name__}){n}")
                dump(v, indent + 1, out)
            else:
                out.append(f"{pad}{k} = {str(v)[:60]} ({type(v).__name__})")
    elif isinstance(tag, list):
        for i, v in enumerate(tag[:max_list]):
            out.append(f"{pad}- #{i}")
            dump(v, indent + 1, out)
        if len(tag) > max_list:
            out.append(f"{pad}  … +{len(tag) - max_list}")


root = read_nbt(sys.argv[1])
lines = []
dump(root, 0, lines)
text = "\n".join(lines)
print(text)
open("nbt_dok.txt", "w", encoding="utf-8").write(text)
