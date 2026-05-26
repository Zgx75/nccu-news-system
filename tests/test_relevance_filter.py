import ast
import pathlib
import types
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_is_relevant_article(module_path: pathlib.Path):
    source = module_path.read_text(encoding="utf-8")
    parsed = ast.parse(source, filename=str(module_path))
    target_func = None

    for node in parsed.body:
        if isinstance(node, ast.FunctionDef) and node.name == "is_relevant_article":
            target_func = node
            break

    if target_func is None:
        raise AssertionError(f"Cannot find is_relevant_article in {module_path}")

    isolated_module = ast.Module(body=[target_func], type_ignores=[])
    ast.fix_missing_locations(isolated_module)
    namespace = types.SimpleNamespace()
    exec(compile(isolated_module, filename=str(module_path), mode="exec"), namespace.__dict__)
    return namespace.is_relevant_article


class RelevanceFilterTests(unittest.TestCase):
    def setUp(self):
        self.targets = [
            load_is_relevant_article(REPO_ROOT / "app.py"),
            load_is_relevant_article(REPO_ROOT / "auto_export.py"),
        ]

    def test_content_keyword_anywhere_is_included(self):
        content = "這篇報導前段都沒提到學校，直到最後才出現政大。"
        for fn in self.targets:
            self.assertTrue(fn("一般標題", content))

    def test_no_keyword_in_title_or_content_is_excluded(self):
        for fn in self.targets:
            self.assertFalse(fn("一般標題", "這篇文章完全沒有相關詞"))

    def test_title_keyword_still_included(self):
        for fn in self.targets:
            self.assertTrue(fn("NCCU 相關報導", ""))


if __name__ == "__main__":
    unittest.main()
