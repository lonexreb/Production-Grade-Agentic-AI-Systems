# Renders docs/media/crash-demo.gif — run from repo root: vhs docs/media/crash-demo.tape
Output docs/media/crash-demo.gif
Set FontSize 13
Set Width 1000
Set Height 520
Set TypingSpeed 40ms
Set Theme "Catppuccin Mocha"
Type "# OpenAgentOS: crash mid-run -> watchdog revives -> exactly one side effect"
Enter
Type "uv run python -m apps.demo.crash_demo 2>/dev/null"
Enter
Sleep 25s
