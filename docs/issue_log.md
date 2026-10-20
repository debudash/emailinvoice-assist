# Issue log

One entry per bug fix. Each issue has a regression test carrying the same ID, and a comment block at the fix site.

| ID | Date | Symptom | Root cause | Fix | Regression test | Commit |
|----|------|---------|------------|-----|-----------------|--------|
| ISSUE-001 | 2026-10-19 | Reference API container exited on first `docker compose up`: `ModuleNotFoundError: No module named 'psycopg'` | Starter `requirements.txt` allowed any `sqlalchemy>=2.0.36`, so the build installed 2.1.5. SQLAlchemy 2.1 maps plain `postgresql://` URLs to psycopg 3, and only psycopg2 is installed. | Pinned `sqlalchemy>=2.0.36,<2.1`. The plain URL is kept because the entrypoint passes it straight to `psycopg2.connect()`. | `services/api/tests/test_issue_001_postgres_driver.py` | `5c45099` |
| ISSUE-002 | 2026-10-19 | First S0 end-to-end run: the context Stage failed with `TypeError: string indices must be integers` while scoring the agent's choices | The mcp 2.x client names structured tool output `structured_content`. The code read the 1.x name `structuredContent`, found nothing, and fell back to the first text block, which holds only one row of a list. | Read `structured_content` and unwrap FastMCP's `{"result": [...]}` wrapper for lists | `tests/test_issue_002_mcp_result_parsing.py` | `4523618` |
