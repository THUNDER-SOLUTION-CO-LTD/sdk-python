"""Compile every README program, type-check it strictly and validate shell syntax."""

from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def test_readme_programs() -> None:
    count = 0
    with tempfile.TemporaryDirectory(prefix="thunder-readme-") as directory:
        programs = []
        for readme in (ROOT / "README.md", ROOT / "README.th.md", ROOT / "examples/README.md"):
            for index, (language, source) in enumerate(
                re.findall(r"^```([^\n]*)\n(.*?)^```\s*$", readme.read_text(), re.M | re.S)
            ):
                count += 1
                if language == "python":
                    compile(source, str(readme), "exec")
                    path = Path(directory) / f"{readme.parent.name}_{readme.stem}_{index}.py"
                    path.write_text(source)
                    programs.append(str(path))
                elif language == "sh":
                    subprocess.run(["sh", "-n"], input=source, text=True, check=True)
                else:
                    raise ValueError(f"Unchecked code language: {language!r} in {readme}")
        if not programs:
            raise ValueError("No Python README programs found")
        subprocess.run([sys.executable, "-m", "mypy", "--strict", *programs], cwd=ROOT, check=True)
    print(f"README check: {count} blocks checked; {len(programs)} standalone Python programs")
