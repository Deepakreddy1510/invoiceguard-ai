import ast

from scripts.dataset_v2.common import DATA, ROOT, load


def test_no_application_or_child_imports_answer_assets():
    files = list((ROOT / "backend/app").rglob("*.py")) + [
        ROOT / "backend/scripts/dataset_v2/child.py"
    ]
    for path in files:
        source = path.read_text()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith(
                    ("evaluation", "scripts.dataset_v2.oracle", "scripts.dataset_v2.runner")
                )
        assert "oracle.json" not in source and "development/answers.json" not in source


def test_related_documents_never_cross_splits():
    docs = load(DATA / "manifest.json")["documents"]
    seen = {}
    for d in docs:
        for key in ["derivation_family", "sha256", "layout"]:
            identity = (key, d[key])
            assert identity not in seen or seen[identity] == d["split"]
            seen[identity] = d["split"]


def test_normal_pytest_configuration_does_not_collect_private_evaluation():
    assert (ROOT / "backend/pyproject.toml").read_text().find('testpaths = ["tests"]') >= 0
    for path in (ROOT / "backend/tests").rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "validate_answers"
            ):
                assert not any(
                    isinstance(arg, ast.Constant) and arg.value == "heldout" for arg in node.args
                )
