# Ubuntu interactive terminal autostart

Installed user Bash hook in /home/tuan/.bashrc; original backup at
/home/tuan/.bashrc.before-signaltrading. Hook runs only for interactive Bash,
unless SIGNALTRADING_DISABLE_AUTOSTART=1. Installer is idempotent and validates
shell syntax. Installation/check never starts bot or sends a message.

Script: /home/tuan/project/myproject/signalcryto/tools/autostart.sh.
On next terminal opening, checks .venv/.env presence and lock, then starts detached
watch with --duration 0 --telegram --env-file absolute-path. No shell source of
secrets. autostart.lock prevents repeated startup and existing SQLite owner lock
avoids launching over a manually running watcher. Runtime DB lock resolves races.

Log: /home/tuan/project/myproject/signalcryto/data/candle-watch/autostart.log.
View: `tail -n 50 /home/tuan/project/myproject/signalcryto/data/candle-watch/autostart.log`.
Processes: `pgrep -af 'python.*signaltrading.watch'`. To stop, inspect listed PIDs
and use `kill -INT <verified-PID>` for only the intended watcher; no broad pkill.
Stopping doesn't disable hook; next interactive terminal opening starts it again.

Disable permanently: comment the `bash .../tools/autostart.sh start` line inside
BEGIN/END SIGNALTRADING_AUTOSTART markers in /home/tuan/.bashrc. Do not restore
entire backup blindly over unrelated subsequent shell edits. Reinstall if needed:
`.venv/bin/python tools/install_autostart.py` from checkout root.

This is shell-open startup, NOT Windows boot/service supervision. No auto-restart
after crash until another terminal opens. WSL shutdown, Windows reboot/sleep or
network loss can interrupt monitoring. nohup is not an uptime guarantee; use a
separately reviewed service configuration for unattended operation. Monitor log
disk growth. Existing foreground watcher may remain running; do not start duplicates.