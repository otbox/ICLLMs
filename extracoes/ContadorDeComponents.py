import json
from pathlib import Path
from typing import Any, Dict, List, Optional

# -----------------------------
# 1) Contar componentes e subcomponentes pela árvore "filhos"
# Regra: cada dict dentro de ui_structure é 1 componente; os filhos entram recursivamente.
# -----------------------------
def count_components_ui_structure(node_or_list: Any, children_key: str = "filhos") -> int:
    count = 0
    stack = [node_or_list]

    while stack:
        x = stack.pop()

        if isinstance(x, dict):
            # conta este nó como componente
            count += 1
            children = x.get(children_key)
            if isinstance(children, list) and children:
                stack.extend(children)

        elif isinstance(x, list):
            # lista de nós
            for item in x:
                if isinstance(item, (dict, list)):
                    stack.append(item)

    return count

# -----------------------------
# 2) Extrair as raízes para contar (ui_structure)
# -----------------------------
def extract_roots(data: Any) -> Dict[str, Any]:
    roots: Dict[str, Any] = {}
    if not isinstance(data, dict):
        return roots

    if isinstance(data.get("ui_structure"), list):
        roots["ui_structure"] = data["ui_structure"]  # [file:64]

    return roots

# -----------------------------
# 3) Analisar 1 arquivo e retornar contagem detectada
# -----------------------------
def analyze_json_file(fp: Path) -> Dict[str, Any]:
    data = json.loads(fp.read_text(encoding="utf-8"))

    roots = extract_roots(data)
    detected_by_origin: Dict[str, int] = {}

    for origin, root in roots.items():
        detected_by_origin[origin] = count_components_ui_structure(root, children_key="filhos")

    detected = detected_by_origin.get("ui_structure")

    return {
        "components": {
            "detectado": detected,
            "detectado_por_origem": detected_by_origin
        }
    }

# -----------------------------
# 4) Varrer pasta e subpastas e gerar o JSON "pasta -> arquivos"
# -----------------------------
def build_folder_report(root_dir: str, json_glob: str = "*.json") -> Dict[str, Any]:
    root_path = Path(root_dir)
    out: Dict[str, Any] = {"pasta": str(root_path.resolve()), "arquivos": {}}

    for fp in root_path.rglob(json_glob):  # recursivo
        if not fp.is_file():
            continue

        rel = str(fp.relative_to(root_path))
        try:
            out["arquivos"][rel] = analyze_json_file(fp)
        except Exception as e:
            out["arquivos"][rel] = {"erro": str(e)}

    return out

if __name__ == "__main__":
    # Exemplo: ajusta para sua pasta raiz
    report = build_folder_report("limeira")

    Path("relatorio_componentes_ui_structure.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
