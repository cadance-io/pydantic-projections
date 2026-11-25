#!/usr/bin/env python3
"""Validate tests follow BDD structure conventions from CLAUDE.md."""

import ast
import sys
import tomllib
from pathlib import Path

# pytest-describe collects a block only under these prefixes. Inside a block,
# it collects every other public function as a test.
with open(Path(__file__).resolve().parent.parent / "pyproject.toml", "rb") as _f:
    _BLOCK_PREFIXES = tuple(
        tomllib.load(_f)["tool"]["pytest"]["ini_options"]["describe_prefixes"]
    )
_CONDITION_PREFIXES = tuple(p for p in _BLOCK_PREFIXES if p != "describe_")


def _parse_file(filepath: Path):
    with open(filepath) as f:
        try:
            return ast.parse(f.read())
        except SyntaxError:
            return None


def _is_fixture(node) -> bool:
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Attribute) and target.attr == "fixture":
            return True
        if isinstance(target, ast.Name) and target.id == "fixture":
            return True
    return False


def _categorize_children(body, *, inside_block: bool = True):
    """Sort functions the way pytest-describe collects them.

    Inside a block, every public function that is not a block is a test,
    whatever its name. At module level, only test_*/it_* names count as tests.
    """
    result = {"describe": [], "when": [], "test": []}
    for node in body:
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if node.name.startswith("describe_"):
            result["describe"].append(node)
        elif node.name.startswith(_CONDITION_PREFIXES):
            result["when"].append(node)
        elif inside_block:
            if not node.name.startswith("_") and not _is_fixture(node):
                result["test"].append(node)
        elif node.name.startswith(("test_", "it_")):
            result["test"].append(node)
    return result


_CONDITION_INFIXES = ("_when_", "_with_", "_without_")


def _check_embedded_conditions(func, filepath: Path) -> list[str]:
    """Flag test/describe names embedding condition keywords."""
    for infix in _CONDITION_INFIXES:
        if infix in func.name:
            keyword = infix.strip("_")
            return [
                f"{filepath}:{func.lineno} - '{func.name}' embeds "
                f"'{infix}' in its name. Extract the condition "
                f"into a nested {keyword}_* block instead. "
                f"Do not rephrase with conjunctions like 'and'."
            ]
    return []


def _validate_module_level(tree: ast.Module, filepath: Path) -> list[str]:
    """Validate module-level test structure.

    At module level, we expect:
    - describe_* functions (top-level organization)
    - No top-level test_* or it_* functions
    - No top-level when_* functions
    """
    violations = []
    children = _categorize_children(tree.body, inside_block=False)

    if children["test"]:
        test_names = [f.name for f in children["test"]]
        violations.append(
            f"{filepath} - Top-level test functions found: {', '.join(test_names)}. "
            f"Tests should be inside describe_* blocks"
        )

    if children["when"]:
        when_names = [f.name for f in children["when"]]
        violations.append(
            f"{filepath} - Top-level when_* functions found: {', '.join(when_names)}. "
            f"when_* blocks should be inside describe_* blocks"
        )

    for describe_func in children["describe"]:
        violations.extend(_validate_describe_block(describe_func, filepath))

    return violations


def _validate_describe_block(describe_func, filepath: Path) -> list[str]:
    """Validate a describe_* block structure.

    In a describe block, we expect:
    - when_* functions for organizing test scenarios
    - OR test_*/it_* functions for simple tests
    - OR nested describe_* for sub-grouping
    - But NOT a mix of when_* and test_*/it_* at the same level
    """
    violations = []
    children = _categorize_children(describe_func.body)

    if children["when"] and children["test"]:
        violations.append(
            f"{filepath}:{describe_func.lineno} - {describe_func.name} contains both "
            f"when_* and test_*/it_* functions. Use either when_* blocks for complex "
            f"scenarios or test_*/it_* directly for simple tests"
        )

    if not any(children[k] for k in children):
        violations.append(
            f"{filepath}:{describe_func.lineno} - {describe_func.name} is empty "
            f"(no when_*, test_*/it_*, or nested describe_* functions)"
        )

    violations.extend(_validate_child_funcs(children, filepath))
    return violations


def _validate_when_block(when_func, filepath: Path) -> list[str]:
    """Validate a when_* block structure."""
    violations = []
    children = _categorize_children(when_func.body)

    if children["describe"]:
        nested_names = [f.name for f in children["describe"]]
        violations.append(
            f"{filepath}:{when_func.lineno} - describe_* inside when "
            f"{when_func.name}: {', '.join(nested_names)}. "
            f"describe blocks should be at higher level"
        )

    if not children["test"] and not children["when"]:
        violations.append(
            f"{filepath}:{when_func.lineno} - {when_func.name} has no test_*/it_* "
            f"functions or nested when_* blocks"
        )

    violations.extend(_validate_child_funcs(children, filepath, skip={"describe"}))
    return violations


def _validate_child_funcs(
    children,
    filepath,
    *,
    skip: set[str] | frozenset[str] = frozenset(),
):
    violations = []
    for func in children.get("when", []):
        if "when" not in skip:
            violations.extend(_validate_when_block(func, filepath))
    for func in children.get("describe", []):
        if "describe" not in skip:
            violations.extend(_validate_describe_block(func, filepath))
    for func in children.get("test", []):
        if "test" not in skip:
            violations.extend(_validate_test_function(func, filepath))
    return violations


def _validate_embedded_conditions_everywhere(
    tree: ast.AST,
    filepath: Path,
) -> list[str]:
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            violations.extend(_check_embedded_conditions(node, filepath))
    return violations


def _validate_test_function(test_func, filepath: Path) -> list[str]:
    """Validate a collected test is a leaf node.

    A block under an unconfigured prefix, such as and_* or given_*, is collected
    as one test: it passes without running the tests nested inside it.
    """
    violations = []
    for node in test_func.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            if node.name.startswith((*_BLOCK_PREFIXES, "test_", "it_")):
                violations.append(
                    f"{filepath}:{test_func.lineno} - {test_func.name} contains "
                    f"nested function {node.name}, so pytest-describe collects "
                    f"{test_func.name} as one test and never runs {node.name}. "
                    f"Name the block with one of {', '.join(_BLOCK_PREFIXES)}"
                )
    return violations


def validate_directory(path: Path) -> int:
    """Validate all test files in directory or a single test file."""
    all_violations = []

    if path.is_file():
        test_files = (
            [path]
            if path.name.startswith("test_") or path.name == "conftest.py"
            else []
        )
    else:
        test_files = list(path.rglob("test_*.py")) + list(path.rglob("conftest.py"))

    for test_file in test_files:
        if "scripts" in test_file.parts or test_file.name.startswith("_"):
            continue

        tree = _parse_file(test_file)
        if tree is not None:
            all_violations.extend(
                _validate_embedded_conditions_everywhere(tree, test_file)
            )
            all_violations.extend(_validate_module_level(tree, test_file))

    if all_violations:
        print("❌ Test validation failed:\n", file=sys.stderr)
        for violation in all_violations:
            print(f"  {violation}", file=sys.stderr)
        print(f"\nTotal violations: {len(all_violations)}", file=sys.stderr)
        return 1

    print(f"✅ All {len(test_files)} test files pass validation", file=sys.stderr)
    return 0


def main():
    """Main entry point."""
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("tests")

    if not path.exists():
        print(f"Error: Path {path} does not exist")
        sys.exit(1)

    sys.exit(validate_directory(path))


if __name__ == "__main__":
    main()
