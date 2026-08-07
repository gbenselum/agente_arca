# Análisis de Falencias y Mejoras — `agente_arca`

**Repositorio:** https://github.com/gbenselum/agente_arca/tree/main  
**Fecha de análisis:** 2026-08-07  
**Stack:** Python 3.x | pypdf | Playwright | Pydantic (declarado, no usado) | pytest

---

## Falencias Críticas

### 1. Browser Automator incompleto (placeholder)

**Archivo:** `src/browser/siradig_automator.py`

El Step 5 del automator es un stub sin implementación real:

```python
# Map code to ARCA dropdown / option button
# Fill fields...
# Click "Guardar" (Draft)
results.append({"siradig_code": siradig_code, "status": "DRAFT_SAVED"})
```

No hay lógica para navegar los formularios de SiRADIG según cada categoría de deducción (educación, médico, alquiler, etc.). El agente reporta `DRAFT_SAVED` sin ejecutar ninguna acción real en el browser.

---

### 2. No hay orquestador / entry point

No existe un `main.py` ni CLI que coordine el pipeline end-to-end:

```
F.572 parse → invoice parse → dedup → validate → compute → upload
```

Todo depende de que un agente LLM externo llame las funciones en el orden correcto. No hay forma de ejecutar el flujo de manera standalone.

---

### 3. Topes anuales NO implementados

**Archivo:** `src/engine/deduction_calculator.py`

El calculator aplica la tasa de deducción (ej. 40% para gastos médicos) pero **ignora completamente** los topes legales que el propio SKILL.md documenta:

| Categoría | Tope que debería aplicar |
|-----------|--------------------------|
| Gastos Médicos | 5% de Ganancia Neta Anual |
| Medicina Prepaga | 5% de Ganancia Neta Anual |
| Gastos de Educación | 40% del MNI Anual |
| Servicio Doméstico | 100% del MNI Anual |
| Alquiler Habitación | Menor entre 40% y 100% MNI |

Esto puede generar montos deducibles incorrectos (sobredeclaración fiscal).

---

### 4. Seguridad de credenciales débil

- La clave fiscal se guarda en texto plano en `.env`
- No hay integración con keychain del OS, secrets managers, ni cifrado
- La función `sync_f572_to_env()` **sobreescribe** el `.env` completo (borra comentarios y líneas que no parsea)

---

### 5. Parser de facturas frágil

**Archivo:** `src/parser/invoice_parser.py`

- Solo usa regex sobre texto extraído con `pypdf` (falla con PDFs escaneados/imagen)
- No hay OCR real (Tesseract, AWS Textract, Google Vision) a pesar de que el README/SKILL mencionan "OCR & Vision extraction"
- Si el PDF tiene un layout diferente al esperado, todos los campos quedan vacíos sin generar warnings

---

## Falencias Moderadas

### 6. Pydantic declarado pero no usado

Está en `requirements.txt` pero todos los datos fluyen como `Dict[str, Any]`. No hay validación de tipos en runtime, ni schemas Pydantic para invoices ni F.572 data. Esto dificulta detectar errores tempranamente.

---

### 7. Manejo de errores insuficiente

- `extract_text_from_pdf` captura `Exception` genérica y retorna `""` — el flujo continúa con datos vacíos sin alertar
- No hay logging estructurado (usa `print()` en todos los módulos)
- No hay retry logic en el browser automator
- No se valida que el JSON generado tenga campos mínimos antes de pasar al siguiente paso

---

### 8. Tests insuficientes

**Archivo:** `tests/test_validator.py`

- Solo 5 unit tests, todos en un archivo
- No hay tests para `invoice_parser.py`
- No hay tests de integración
- No hay fixtures con PDFs de ejemplo
- El test `test_validate_cuit_format` usa un CUIT hardcoded que puede no representar todos los edge cases (prefijos 20, 23, 24, 27, 30, 33, 34)

---

### 9. MCP schema desconectado del código

`mcp_tools_schema.json` define 4 tools pero:
- No hay servidor MCP (stdio o HTTP) que las exponga
- La tool `generate_siradig_payload` no tiene implementación en ningún módulo del `src/`
- No hay binding entre el schema y las funciones Python

---

### 10. `sync_f572_to_env` destructivo

**Archivo:** `src/parser/f572_parser.py`

Reescribe el `.env` completo perdiendo:
- Comentarios del usuario
- Variables no relacionadas con F.572 (ej. `BROWSER_HEADLESS`, `BROWSER_SLOWMO_MS`) si no estaban en el map parseado
- El orden y agrupación original del archivo

---

## Mejoras Propuestas

| Prioridad | Mejora | Descripción |
|-----------|--------|-------------|
| **Alta** | Implementar automator completo | Mapear cada `siradig_code` a su flujo de navegación real en SiRADIG (selectores, dropdowns, campos por categoría). Agregar screenshots de verificación en cada paso. |
| **Alta** | Implementar topes anuales | Agregar al engine las constantes de MNI y GNA del período fiscal, y calcular topes reales por categoría según RG 4003/17. |
| **Alta** | Agregar OCR real | Integrar Tesseract o un servicio cloud (AWS Textract / Google Vision) como fallback cuando `pypdf` no extrae texto útil de PDFs escaneados. |
| **Alta** | CLI / orquestador | Crear `main.py` con `argparse` o `click` que ejecute el pipeline completo o pasos individuales (`parse`, `validate`, `compute`, `upload`). |
| **Media** | Modelos Pydantic | Definir `InvoiceData`, `F572Data`, `DeductionResult` como modelos Pydantic con validación estricta de tipos y campos obligatorios. |
| **Media** | Logging estructurado | Reemplazar `print()` por `logging` con niveles (INFO, WARNING, ERROR) y formato configurable (JSON para producción, human-readable para dev). |
| **Media** | Proteger `.env` sync | No sobreescribir el archivo completo; usar `python-dotenv`'s `set_key()` para actualizar solo las keys relevantes sin destruir el resto. |
| **Media** | MCP server real | Implementar un servidor MCP (FastMCP o stdio) que exponga las tools del schema y las conecte al código real. |
| **Media** | Tests robustos | Agregar tests para el parser (con PDFs de fixture), edge cases del validator (CUITs con distintos prefijos, fechas límite), tests del calculator con topes, y mocks para el browser. |
| **Baja** | CI/CD | Agregar GitHub Actions con lint (`ruff`), tests (`pytest`), y type checking (`mypy`). |
| **Baja** | Secrets management | Integrar con keyring del OS o al menos advertir al usuario si la clave fiscal está en texto plano. Considerar cifrado at-rest. |
| **Baja** | Documentación de selectores ARCA | Documentar los selectores CSS/XPath del portal ARCA que usa el automator con fecha de verificación, ya que el portal cambia frecuentemente. |

---

## Resumen Ejecutivo

El repo tiene una **buena arquitectura conceptual** y documentación clara (SKILL.md y README bien estructurados), pero está en estado de **prototipo/esqueleto**. Los gaps más graves son:

1. El automator no ejecuta acciones reales en el browser
2. Los cálculos fiscales son incompletos (sin topes anuales)
3. Los parsers no manejan PDFs escaneados (sin OCR)
4. No hay forma de ejecutarlo sin un agente LLM externo

**Prioridades de implementación sugeridas:**

```
automator real > topes fiscales > OCR fallback > CLI orquestador
```

---

