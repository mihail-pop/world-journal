# World Journal repository instructions

- Before planning or editing, read APP_CONTEXT.md completely. It is the authoritative product and architecture specification.
- Never modify APP_CONTEXT.md unless explicitly asked.
- Implement only the phase or task explicitly requested. Do not attempt the entire application in one pass.
- Use Django templates, HTMX, CSS, and small vanilla JavaScript ES modules.
- Do not introduce React, Vue, Vite, Node build tooling, accounts, Redis, Celery, Docker-only setup, or paid APIs.
- Keep dependencies minimal and update requirements.txt whenever a Python dependency changes.
- Preserve direct URL loads and progressive enhancement alongside HTMX navigation.
- Use the workspace .venv interpreter for all Python commands.
- Run python manage.py check and python manage.py test after changes.
- Do not commit changes; leave them for the user to review.