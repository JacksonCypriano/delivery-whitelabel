#!/usr/bin/env python3
"""Reproducible reference inventory; absence of a static match never permits deletion."""
import ast
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test_sqlite")
import django
django.setup()
from django.urls import URLPattern, get_resolver

routes = []
def visit(patterns, prefix=""):
    for p in patterns:
        path = prefix + str(p.pattern)
        if isinstance(p, URLPattern):
            callback = p.callback
            owner = getattr(callback, "view_class", None) or getattr(callback, "cls", None) or callback
            routes.append({"url": path, "view": f"{owner.__module__}.{owner.__name__}", "name": p.name})
        else:
            visit(p.url_patterns, path)
visit(get_resolver().url_patterns)

sources = {}
for parent in ("apps", "templates", "static/js", "scripts", "docs", "config"):
    for p in (ROOT / parent).rglob("*"):
        if p.is_file() and p.suffix in {".py", ".html", ".txt", ".js", ".md", ".sh"} and "__pycache__" not in p.parts:
            if "template-inventory" in p.name or p.name == "inventory_templates.py": continue
            sources[str(p.relative_to(ROOT))] = p.read_text(errors="replace")

owners = {}
for path, content in sources.items():
    if not path.startswith("apps/") or not path.endswith(".py") or "/migrations/" in path or "test" in path: continue
    try: tree = ast.parse(content)
    except SyntaxError: continue
    module = path[:-3].replace("/", ".")
    imports = {"models": [], "forms": [], "dependencies": []}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            key = "models" if "models" in (node.module or "") else "forms" if "forms" in (node.module or "") else "dependencies"
            imports[key].extend(f"{node.module}.{item.name}" for item in node.names)
    def collect(node, owner=None):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            owner = f"{module}.{node.name}" if not owner or isinstance(node, ast.ClassDef) else owner
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.endswith((".html", ".txt")):
            if (ROOT / "templates" / node.value).is_file():
                entry = {"view": owner or module, "file": path, "line": node.lineno, **imports}
                owners.setdefault(node.value, []).append(entry)
        for child in ast.iter_child_nodes(node): collect(child, owner)
    collect(tree)

rows = []
for p in sorted((ROOT / "templates").rglob("*")):
    if not p.is_file(): continue
    name = str(p.relative_to(ROOT / "templates"))
    text = p.read_text(errors="replace")
    direct_owners = owners.get(name, [])
    refs = [{"file": path, "lines": [n for n, line in enumerate(content.splitlines(), 1) if name in line]} for path, content in sources.items() if name in content and path != f"templates/{name}"]
    parent_names = [ref["file"][10:] for ref in refs if ref["file"].startswith("templates/")]
    effective = list(direct_owners)
    checked = set()
    queue = parent_names[:]
    while queue:
        parent = queue.pop()
        if parent in checked: continue
        checked.add(parent)
        effective += owners.get(parent, [])
        queue += [path[10:] for path, content in sources.items() if path.startswith("templates/") and parent in content and path != f"templates/{parent}"]
    view_names = {item["view"] for item in effective}
    paths = [route for route in routes if route["view"] in view_names]
    # Ancestor layouts carry scripts/links used by a leaf page.
    template_sources = [text]
    queue = re.findall(r'{%\s*(?:extends|include)\s+[\'"]([^\'"]+)', text)
    visited = set()
    while queue:
        dep = queue.pop()
        if dep in visited: continue
        visited.add(dep)
        source = sources.get(f"templates/{dep}", "")
        template_sources.append(source)
        queue += re.findall(r'{%\s*(?:extends|include)\s+[\'"]([^\'"]+)', source)
    combined = "\n".join(template_sources)
    if name.startswith("admin/super"): audience = "SuperAdmin (legado)"
    elif name.startswith(("admin/", "billing/", "dashboard/")): audience = "Lojista/administrador (legado)"
    elif name.startswith("accounts/") and ("email" in name or name.endswith(".txt")): audience = "Destinatário de email; não é tela"
    elif name.startswith("accounts/"): audience = "Cliente/visitante; sessão e OTP conforme view"
    elif name == "merchant/shell.html": audience = "Shell React do painel; host define o papel"
    else: audience = "Público/cliente ou componente compartilhado"
    tests = sorted({ref["file"] for ref in refs if "test" in ref["file"]})
    for route in paths:
        for path, content in sources.items():
            if "test" in path and path.endswith(".py") and (route["view"].split(".")[-1] in content or (route["name"] and route["name"] in content)):
                tests.append(path)
    area = name.split("/")[0]
    proposed = {"stores": "Storefront/Catalog/Product", "checkout": "Cart/Checkout/Review/Payment/Success", "orders": "OrderHistory", "accounts": "CustomerAccount/Auth", "marketplace": "Marketplace/Marketing SSR", "legal": "Legal SSR", "billing": "Finance (React existente; revisar fallbacks)", "admin": "ResourceList/ResourceDetail (React existente; revisar fallbacks)", "merchant": "App (existente)"}.get(area, "Layout compartilhado")
    from apps.public_ui.rendering import PAGES
    migrated_public = name in PAGES
    rows.append({"template": name, "audience": audience, "views": direct_owners, "shared_view_usage": effective,
        "routes": paths, "function": f"Interface/componente {area}; regras mantidas nas views e serviços indicados",
        "existing_apis": sorted({r["url"] for r in routes if ("api/" in r["url"] and (r["view"].split(".")[1:2] == [area]))}),
        "react_target": proposed, "models": sorted({model for o in effective for model in o["models"]}),
        "forms": sorted({form for o in effective for form in o["forms"]}),
        "dependencies": sorted({dep for o in effective for dep in o["dependencies"]}),
        "template_dependencies": sorted(visited),
        "javascript": sorted(set(re.findall(r'[\'\"]([^\'\"]+\.js(?:\?[^\'\"]*)?)[\'\"]', combined))),
        "named_links": sorted(set(re.findall(r'{%\s*url\s+[\'\"]([^\'\"]+)', combined))),
        "references_including_email_tasks_tests": refs, "tests": sorted(set(tests)),
        "migrated": migrated_public or name == "merchant/shell.html", "safe_to_remove": False,
        "reason_to_keep": "Shell de montagem React" if name == "merchant/shell.html" else "Rota renderizada por React SSR; arquivo preservado para comparação de paridade em homologação" if migrated_public else "Email, componente compartilhado ou fallback administrativo explícito; preservar referências até homologação",
        "limitations": "Inventário estático: imports são dependências do módulo, não prova de uso por caminho; callbacks dinâmicos/admin e links externos exigem revisão. Ausência de referência não comprova desuso."})
out = ROOT / "docs/packages"
out.mkdir(parents=True, exist_ok=True)
(out / "package-14-template-inventory.json").write_text(json.dumps({"templates": rows, "routes": routes}, ensure_ascii=False, indent=2))
lines = ["# Pacote 14 — auditoria de templates após migração", "", f"{len(rows)} arquivos locais catalogados. Nenhum está autorizado para remoção.", "", "Inventário de referências e propostas de destino, não atestado de paridade. O JSON acompanha views, linhas, imports de models/forms, scripts, links, dependências, testes e referências. Templates de bibliotecas instaladas não fazem parte desta contagem.", "", "| Template | URL / view resolvida | Função / destino React | Testes diretos | Migrado? | Remover? |", "|---|---|---|---|---|---|"]
for row in rows:
    paths = "; ".join(route["url"] for route in row["routes"]) or "; ".join(item["view"] for item in row["views"]) or "Compartilhado/legado: conferir referências JSON"
    lines.append(f"| `{row['template']}` | {paths.replace('|', '/')} | {row['react_target']} | {len(row['tests'])} | {'React / SSR' if row['migrated'] else 'Email / compartilhado / fallback'} | Não |")
(out / "package-14-template-inventory.md").write_text("\n".join(lines) + "\n")
print(f"Inventário: {len(rows)} templates; {len(routes)} rotas resolvidas.")
