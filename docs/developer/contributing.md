# Contributing

If you want to fix a bug, improve the documentation or add a focused feature, contributions are welcome. For a large change, open an issue first so the direction can be discussed before you spend time rebuilding a major part of the app.

## Development Setup

Follow the setup guide for your operating system, then install the development requirements instead of the runtime file alone:

=== "Windows"

    ```powershell
    .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
    ```

=== "Mac and Linux"

    ```sh
    .venv/bin/python -m pip install -r requirements-dev.txt
    ```

Run Django from the repository root. The app uses direct source files and does not have a frontend build step.

## Project Rules

Keep changes consistent with the existing architecture:

- use Django templates, HTMX, CSS and small vanilla JavaScript modules;
- preserve direct URL loads and progressive enhancement;
- do not add accounts, a separate frontend framework, Redis, Celery or required Docker infrastructure without an explicit project decision;
- keep dependencies minimal;
- preserve the shell-owned video player and notification system;
- preserve retained page state when changing top-level navigation;
- use source adapters for feed-specific behavior;
- update backup mappings when stored models change.

Adventure map artwork and country colors have their own established rendering path. Hover and selection use feature-state line layers above ordinary artwork. Do not replace that with geometry rebuilding or per-hover layer changes.

## Validation

Use the workspace virtual environment for Python commands:

=== "Windows"

    ```powershell
    .\.venv\Scripts\python.exe manage.py check
    .\.venv\Scripts\python.exe manage.py test
    git diff --check
    ```

=== "Mac and Linux"

    ```sh
    .venv/bin/python manage.py check
    .venv/bin/python manage.py test
    git diff --check
    ```

Tests should use local fixtures rather than depending on live news publishers.

## Documentation

The documentation uses Material for MkDocs, matching the structure used by Media Journal.

Preview it locally with:

=== "Windows"

    ```powershell
    .\.venv\Scripts\python.exe -m mkdocs serve
    ```

=== "Mac and Linux"

    ```sh
    .venv/bin/python -m mkdocs serve
    ```

When the public repository and GitHub Pages are ready, publish the site with:

```sh
python -m mkdocs gh-deploy
```

That command builds the site and writes the generated files to the `gh-pages` branch. Do not commit the local `site/` build directory.

## Pull Requests

Keep a pull request focused on one problem. Explain what changed, mention any migrations or generated assets and include the manual checks that matter for the affected workflow.

Do not commit personal databases, uploaded media, backup staging files or virtual environments. Those paths are already ignored by Git.
