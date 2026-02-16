# UI / Browser Tests

Automated tests for the Next.js frontend and Flutter consumer app.

| Script | What It Tests |
|---|---|
| `test_browser_complete.py` | Selenium-based end-to-end browser test covering dashboard, fraud score display, navigation |
| `test_ui_components.py` | Component-level rendering: charts, tables, alerts, responsive layout |

## Running

```bash
# Start the Next.js dev server first
cd frontend/frontend && npm run dev -- -p 3006

# Run browser tests (requires Chrome + chromedriver)
python tests/ui/test_browser_complete.py

# Run component tests
python tests/ui/test_ui_components.py
```
