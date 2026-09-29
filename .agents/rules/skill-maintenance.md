# Skill Maintenance Rule

After completing **any task** that changes the structure, behaviour, or knowledge
of the MacroScope project, you MUST update the relevant skill files before
finishing your response. This is not optional.

## What counts as a structural change

- Adding, removing, or renaming a module in `src/`
- Modifying a module's public API (new/removed/renamed functions or parameters)
- Adding or altering a DB table or column in `macroscope.db`
- Changing the signal algorithm in `quant.py`
- Changing how data is stored or loaded (e.g. price format, timestamp convention)
- Moving files between directories
- Adding a new dependency to `pyproject.toml` or `requirements.txt`
- Changing the entry point or pipeline orchestration in `integration.py`
- Any change to the notebook setup cell or `sys.path` bootstrap

## Which skill to update

| Change area | Skill to update |
|-------------|----------------|
| Module API, DB schema, architecture, data flow | `macroscope-project` |
| yfinance usage pattern, new data source, new indicator | `yfinance-pipeline` |
| Both | Update both |

## Skill file locations

- `.agents/skills/macroscope-project/SKILL.md`
- `.agents/skills/yfinance-pipeline/SKILL.md`

## What to update inside the skill

- **New module**: add its entry to the directory layout, module contracts table,
  data flow diagram, and "Extending the Project" section.
- **Changed function signature**: update the contracts table and any code examples.
- **New DB column or table**: update the schema section and any relevant patterns.
- **New gotcha or pattern discovered**: add it to the appropriate skill section.
- **Deleted or archived file**: remove it from the active layout; note it in `_old/`
  if applicable.

## How to update

Edit the SKILL.md file directly using the file editing tools.
Keep entries concise and accurate — skills are reference material, not prose.
Do not duplicate information that already exists in the source code itself;
instead, document the *why* and the *gotchas* that are not obvious from the code.
