"""Idempotently install an interactive Bash hook, without starting the watcher."""

from pathlib import Path
import shutil
import shlex
import subprocess


def main():
    root = Path(__file__).resolve().parents[1]
    script = root / "tools" / "autostart.sh"
    subprocess.run(["bash", "-n", str(script)], check=True)
    rc = Path.home() / ".bashrc"
    text = rc.read_text() if rc.exists() else ""
    begin = "# BEGIN SIGNALTRADING_AUTOSTART"
    end = "# END SIGNALTRADING_AUTOSTART"
    block = (f"{begin}\n"
             'if [[ $- == *i* && ${SIGNALTRADING_DISABLE_AUTOSTART:-0} != 1 ]]; then\n'
             f"    bash {shlex.quote(str(script))} start\n"
             f"fi\n{end}\n")
    if (begin in text) != (end in text) or text.count(begin) > 1 or text.count(end) > 1:
        raise SystemExit("Invalid existing hook markers; no changes made")
    if begin in text:
        start = text.index(begin)
        finish = text.index(end) + len(end)
        if finish < start:
            raise SystemExit("Invalid marker order; no changes made")
        replacement = text[:start] + block.rstrip("\n") + text[finish:]
    else:
        replacement = text.rstrip("\n") + "\n\n" + block
    backup = rc.with_name(".bashrc.before-signaltrading")
    if rc.exists() and not backup.exists():
        shutil.copy2(rc, backup)
    # Validate proposed shell configuration without executing it.
    subprocess.run(["bash", "-n"], input=replacement, text=True, check=True)
    if replacement != text:
        rc.write_text(replacement)
    print("Installed interactive Ubuntu Bash hook. Watcher NOT started by installer.")
    print(f"Hook script: {script}")
    print(f"Backup: {backup}")


if __name__ == "__main__":
    main()