# Notes for Claude

## Numbers: always the standard format, never the system locale

The program runs on Windows machines set to other languages (e.g. French, where
the decimal separator is ","). Numbers must always be shown and read in the
standard format (`1234.5`, no group separator), unless a task explicitly asks
for the system format.

Whenever code shows, reads, parses or writes numbers, check whether it follows
the standard format or the system settings, and default to the standard one:

- Qt: `src/quickalignment/ui/_qt.py` sets `QLocale.c()` as the default locale on
  import (`use_standard_numbers()`). New windows/entry points must import Qt via
  `._qt`, and never call `setLocale(QLocale.system())` or a language locale on
  spin boxes, validators or `QLocale().toString()`.
- Python: use `float()`, `int()`, f-strings / `format()`; never `locale.atof`,
  `locale.format_string`, `locale.setlocale` or the `"n"` format spec.
- matplotlib: keep `axes.formatter.use_locale` False (the default).
- Files (sessions, configs, CSV): write and read with "." only.

## Agent interface: ARPES viewer is the reference

The MCP server (`src/quickalignment/agent/mcp_server.py`) follows the conventions of ARPES viewer's
`arpes_viewer/agent/protocol.py` (protocol versions, `readOnlyHint`, tool errors, error texts). After changing a
tool, the agent API or the workflow text:

1. put a new tool that changes anything in `ACTING` (mcp_server.py);
2. run `python -m quickalignment.agent.catalog --write` (with `src/` on the path) to regenerate
   `src/quickalignment/agent/API.md`; `tests/test_catalog.py` fails while it is out of date.
