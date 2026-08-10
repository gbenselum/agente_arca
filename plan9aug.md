# Code Analysis & Remediation Plan — `agente_arca`

**Date:** 2026-08-09
**Scope:** Full codebase analysis (18 source files + 7 test files, ~2,665 LOC)
**Status:** All 21 tests pass; 4 critical bugs identified in Phase 1 analysis.

---

## 1. Critical Bugs (functional — surface in real use)

### BUG 1 — `compute_batch_deductions()` crashes 100% of the time
- **File:** `src/engine/deduction_calculator.py:210`
- **Issue:** Passes `total_net_of_pocket=` but model field is `total_net_out_of_pocket` (`src/models/deduction.py:38`). Required field, no default -> Pydantic v2 `ValidationError` on every call.
- **Impact:** `validate`, `pipeline`, `upload-draft` CLI paths crash whenever a valid invoice reaches the compute step.
- **Untested:** `tests/test_deduction_calculator.py` imports `compute_batch_deductions` but never calls it.

### BUG 2 — OCR fallback is non-functional
- **File:** `src/parser/invoice_parser.py:63`
- **Issue:** `pytesseract.image_to_string(pdf_path, ...)` receives a PDF path; Tesseract cannot read PDFs (needs an image). `PIL.Image` import is unused.
- **Impact:** OCR fallback for scanned invoices always fails and silently returns `""`.

### BUG 3 — Sample/demo data fails its own validator
- **Files:** `invoices/*.json`, `vistaprevia/F572_2026_ejemplo.json`, `.env.example`
- **Issue:** CUITs `30711234567`, `30654321098`, `27589876543`, `20123456789` all fail Modulo 11. `validate` rejects every sample invoice.

### BUG 4 — Upload step doesn't filter validated invoices
- **File:** `main.py:151-158` (`cmd_pipeline`)
- **Issue:** Re-reads ALL `invoices/*.json` and uploads them to SiRADIG, including invalid/duplicate ones.

---

## 2. Dead Code Inventory

### Unused imports (production)
| File | Unused imports |
|---|---|
| `main.py` | `List` (17), `compute_deduction` + `generate_siradig_payload` (26) |
| `src/browser/siradig_automator.py` | `os`, `Optional`, `ReceiptType`, `Page`, `BrowserContext`, `PlaywrightTimeoutError` (16) |
| `src/parser/invoice_parser.py` | `os`, `Dict`, `Any`, `Tuple`, `Image` (24) |
| `src/parser/f572_parser.py` | `os`, `List`, `Optional` |
| `src/engine/deduction_calculator.py` | `SiRADIGCategory`, `DeductionResult` |
| `config/settings.py` | `Optional` |
| `src/utils/env_manager.py` | `os`, `Optional` |
| `src/mcp/server.py` | `InvoiceData` (17) |
| `src/models/automator.py` | `Dict`, `Any` |

### Dead model
- `DeductionResult` (`src/models/deduction.py:17`) — never instantiated; `compute_deduction()` returns plain dict.

### Dead configuration
- `settings.browser_headless`, `settings.auto_save_draft` (`config/settings.py:34,36`) — never read by any code.

### Dead model fields
- `AutomatorBatchResult.skipped_count`, status `"SKIPPED"` — no code path produces them.
- `InvoiceData.invoice_id` — computed property, but sample JSONs store a string that Pydantic silently discards.

### Unused test imports
- `test_deduction_calculator.py` (`compute_batch_deductions`, `InvoiceData`, `SiRADIGCategory`)
- `test_f572_parser.py` (`Path`, `parse_f572_pdf_text`)
- `test_validator.py` (`parse_f572_pdf_text`, `InvoiceData`, `ReceiptType`, `SiRADIGCategory`, `DependentModel`, `F572Data`)
- `test_models.py` (`ReceiptType`, `F572LoadedInvoice`, `FiscalYearCaps`, `DeductionResult`)
- `test_legal_validator.py` (`validate_invoice_legal_requirements`)

> `src/utils/__init__.py` and `src/models/__init__.py` re-exports are intentional (via `__all__`) — not dead code.

---

## 3. Code Quality Evaluation

### Strengths
- Clean layered architecture (models / parser / validator / engine / browser / utils / mcp).
- Pydantic v2 models with CUIT-cleaning validators, typed signatures, good docstrings.
- Secret masking (`SensitiveFilter`) in logging.
- Strict draft-mode guardrail in automator + screenshot audit trail.
- Non-destructive `.env` sync via `dotenv.set_key()`.

### Weaknesses
1. Dict-based data flow despite having models (`compute_deduction` returns `dict`).
2. Fragile single-pass regex parsing; `detect_suggested_category` defaults to `GASTOS_EDUCACION` for unknown input (semantically wrong).
3. Hardcoded financial constants with "Proyectados/Estimados" figures for 2025/2026.
4. Untested and brittle Playwright automator (hardcoded selectors, no retry).
5. Hand-rolled JSON-RPC MCP server; `tools/list` reads schema relative to CWD.
6. No packaging (`pyproject.toml` absent), sys.path hacks, no lint/type-check/CI.
7. `upload-draft` aliases full pipeline (sync+parse+validate+upload).
8. `process_pdf_invoice` success semantics: amount > 0 -> success even with warnings.
9. Test gaps: no test for `compute_batch_deductions`, CLI, automator, or `env_manager`.

---

## 4. Remediation Roadmap

### Phase 1 — Fix critical bugs
1. Fix `deduction_calculator.py:210` keyword -> `total_net_out_of_pocket`; add end-to-end test for `compute_batch_deductions`.
2. `invoice_parser.py`: real OCR — rasterize PDF pages (pdf2image/PyMuPDF) -> `PIL.Image` -> `pytesseract`, or gate OCR behind image inputs.
3. `main.py` `cmd_pipeline`: filter uploads to validated, non-duplicate invoice subset.
4. Refresh sample JSONs + `.env.example` with Modulo-11-valid CUITs.

### Phase 2 — Remove dead code
5. Delete unused imports across all files in section 2.
6. Use `DeductionResult` model in `compute_deduction` (or remove it).
7. Remove/wire `settings.browser_headless`, `settings.auto_save_draft`, `skipped_count`/`SKIPPED`.

### Phase 3 — Structural improvements
8. Add `pyproject.toml` + ruff/mypy; fix MCP schema path relative to `__file__`.
9. Change `detect_suggested_category` fallback to `UNKNOWN` instead of education.
10. Expand tests: CLI integration, automator with mocked Playwright, `env_manager`, OCR fallback.
11. Mark 2026 caps for review before production.

### Phase 4 — Optional polish
12. Remove legacy `validate_invoice_legal_requirements` wrapper if unused; make `upload-draft` a true single-step command.

---

## Status Log
- 2026-08-09: Plan saved. Phase 1 implementation started.
- 2026-08-09: **Phase 1 COMPLETE** — all 4 critical bugs fixed, 26 tests passing (5 new tests added).
  - BUG 1: `deduction_calculator.py:210` keyword fixed to `total_net_out_of_pocket`. Added `test_compute_batch_deductions_end_to_end` + `test_compute_batch_deductions_cumulative_cap`.
  - BUG 2: OCR fallback rewritten — PDFs rasterized via PyMuPDF (primary) / pdf2image (fallback) into PIL images before Tesseract; image files handled directly; unsupported types rejected. Added `PyMuPDF>=1.23.0` to requirements + 3 OCR tests.
  - BUG 3: Sample data refreshed with Modulo-11-valid CUITs (`20780009188`, `20517462706`, `27042489943`, `30117368544`, `30200798909`) in `invoices/*.json`, `vistaprevia/F572_2026_ejemplo.json`, and `.env.example`.
  - BUG 4: `cmd_pipeline` upload step now reuses `collect_validated_invoices(args, verbose=False)` — only validated, non-duplicate invoices are uploaded; pipeline aborts upload gracefully when none are eligible. Bonus: single report print in pipeline.
- 2026-08-09: **Phase 2 COMPLETE** — dead code removed. pyflakes clean on `main.py`, `config/`, `src/`, `tests/`; 26 tests still passing.
  - Removed 19 unused imports across `main.py`, `src/engine/deduction_calculator.py`, `src/mcp/server.py`, `src/models/automator.py`, `src/parser/f572_parser.py`, `src/browser/siradig_automator.py`, `src/utils/env_manager.py`, `config/settings.py`, and all test files.
  - `compute_deduction` now returns a typed `DeductionResult` model (was `Dict`) — all callers/tests updated to attribute access; MCP tool serializes via `model_dump()`. The previously-dead model is now genuinely used.
  - Removed dead config `settings.browser_headless` + `settings.auto_save_draft` (+ `.env.example` entries).
  - Removed dead field `AutomatorBatchResult.skipped_count` and `"SKIPPED"` status.
  - Verified every domain model in `src/models/` is referenced by production code.
- 2026-08-09: **Phase 3 IN PROGRESS** — tooling & typing hardening.
  - Added `pyproject.toml` (setuptools packaging, ruff + mypy + pytest config). Installed ruff 0.16.2 & mypy 2.3.0 in `.venv`.
  - Ran `ruff check --fix` (179 auto-fixes) + `ruff format` across repo — modernized typing to PEP 585/604 (`dict`/`list`/`X | None`), sorted imports & dunder `__all__`.
  - Fixed remaining ruff lints manually (E501 long lines, SIM108 ternaries, SIM105 contextlib.suppress) — `ruff check` and `ruff format --check` now both pass.
  - Mypy: fixed 48 errors → **0 issues in 18 files** (run with `--explicit-package-bases`). Changes:
    - Optional third-party imports (`PdfReader`, `sync_playwright`, `pytesseract`, `Image`, `pymupdf`, `convert_from_path`) typed as None-fallbacks with explicit `is None` guards + targeted `# type: ignore[assignment]`.
    - `parse_f572_pdf_text` refactored from heterogeneous `dict` to typed locals + direct `F572Data(...)` construction (eliminated ~15 union-attr errors).
    - `parse_invoice_text` `extracted` dict annotated `dict[str, Any]`.
    - Covariant `Sequence` params for `compute_batch_deductions`, `generate_siradig_payload`, `run_draft_upload`, `validate_invoice_detailed`/`validate_invoice_legal_requirements` (fixes list-invariance at `main.py` call sites).
    - `TOOLS` dispatch map typed `dict[str, Callable[..., Any]]`; `payload` dict annotated `dict[str, Any]`.
    - pymupdf page iteration rewritten (`.pages()` explicit loop, no reliance on `Document.__iter__`).
  - MCP `tools/list` now resolves `mcp_tools_schema.json` from repo root via `__file__` (CWD-independent). Regression test confirmed passing.
  - Verification: `pytest` 26/26 pass, `ruff check` clean, `ruff format --check` clean, `mypy` clean.
- 2026-08-09: **Phase 3 COMPLETE** — structural improvements shipped. 40 tests passing, ruff clean, mypy clean (28 files).
  - `pyproject.toml` added (setuptools packaging, ruff py310/line-length 120, mypy, pytest) — verified tooling: ruff 0.16.2, mypy 2.3.0.
  - MCP `tools/list` schema path now resolved from repo root via `__file__` (CWD-independent).
  - `detect_suggested_category` now returns `SiRADIGCategory.UNKNOWN` for unmatched text (was silently GASTOS_EDUCACION). Added `UNKNOWN` enum member; `InvoiceData.suggested_category` default → `UNKNOWN`; engine fallbacks for dict inputs → `"UNKNOWN"`; automator now REJECTS UNKNOWN items (FAILED status, no browser fill) instead of silently filing as education. Added parser + automator regression tests.
  - New tests (39 → 40 total): `tests/test_env_manager.py` (4), `tests/test_siradig_automator.py` (5, mocked Playwright incl. UNKNOWN rejection + draft-save guardrail), `tests/test_cli.py` (3, end-to-end duplicate/legal filtering + summary output).
  - Robustness: `safe_update_env` now wraps file creation in try/except — bad paths return `False` instead of raising.
  - Estimated fiscal caps: 2025/2026 marked `(NO OFICIAL)` in notes; `ESTIMATED_CAP_YEARS` registry + runtime `logger.warning` in `get_fiscal_caps`; README warning block added; regression test asserts the warning fires only for estimated years.
- 2026-08-09: **Phase 4 COMPLETE** — polish items shipped. 42 tests passing, ruff + mypy clean.
  - Removed legacy `validate_invoice_legal_requirements` wrapper (dead in production, only a test referenced it). `tests/test_validator.py` migrated to `validate_invoice_detailed` (structured `ValidationResult`).
  - `upload-draft` is now a TRUE single-step command: new `cmd_upload_draft()` collects the validated, non-duplicate subset and uploads — it no longer re-runs `sync-f572` + `parse-invoices` + `validate` (which is what `pipeline` is for). `pipeline --upload-draft` still runs all 4 steps. CLI help text updated.
  - New tests: `cmd_upload_draft` is single-step (sync/parse/validate NOT called, upload gets exactly the eligible subset) + skips browser when no valid invoices.
