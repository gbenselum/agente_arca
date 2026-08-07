# Skill: ARCA SiRADIG F.572 Web Automation & Invoice Processing Agent

## 1. System Overview & Purpose

This skill equips the **Antigravity AI Agent** to process, legally validate, deduplicate, and load tax deduction receipts (*facturas*) directly into **ARCA / AFIP - SiRADIG Trabajador (Formulario 572 Web)** in **DRAFT mode** (`Borrador`).

The agent follows a 2-step verification & extraction workflow:
1. **F.572 PDF Extraction & `.env` Sync**: Inspects the `vistaprevia/` folder for the current F.572 export PDF, extracts its content into a JSON file (`vistaprevia/<pdf_name>.json`), **automatically loads taxpayer & dependent parameters into `.env`**, and checks candidate invoices against existing loaded receipts to avoid duplicates.
2. **Legal Validation & Draft Upload**: Validates CUIT, CAE, and fiscal limits under **RG 4003/17**, computes eligible deductible amounts, cross-references family dependents in `.env`, and uses Playwright browser automation to save new items as drafts in SiRADIG without performing final submission (`Guardar Borrador`).

---

## 2. Folder Architecture & Workflow

```
agente_arca/
├── .env.example                # Example environment file with credentials & dependents template
├── .env                        # Protected local environment variables (Git ignored!)
├── .gitignore                  # Strict Git rules preventing secret leaks
├── SKILL.md                    # Comprehensive Skill & Tax Validation specification
├── mcp_tools_schema.json       # MCP Tools definition for LLM integration
├── vistaprevia/                # 📍 Place official F.572 "Vista Previa" PDFs here
│   ├── F572_2026.pdf           # Input F.572 export PDF
│   └── F572_2026.json          # Automatically extracted JSON mirror
├── invoices/                   # 📍 Place incoming PDF invoices here
│   ├── factura_colegio_01.pdf  # Input invoice PDF
│   └── factura_colegio_01.json # Automatically extracted JSON mirror
├── config/
│   └── settings.py             # Environment configuration & credential manager
├── src/
│   ├── parser/
│   │   ├── invoice_parser.py   # OCR & Vision extraction of receipt metadata to JSON
│   │   └── f572_parser.py      # Extraction of F.572 Vista Previa PDFs, .env sync & duplicate check
│   ├── validator/
│   │   └── legal_validator.py  # Validation of CUIT, CAE, Fiscal dates & Dependents
│   ├── engine/
│   │   └── deduction_calculator.py # Math engine for deductible caps and rates (RG 4003/17)
│   └── browser/
│       └── siradig_automator.py # Playwright browser automation for ARCA SiRADIG
└── tests/
    └── test_validator.py       # Unit tests for tax logic & duplicate detection
```

---

## 3. Workflow Steps

```
 [1. F.572 PDF Ingestion (vistaprevia/)]
            |
            v
 [f572_parser] --------> Creates vistaprevia/<f572_name>.json
            | ---------> ⚡ Auto-populates .env with Taxpayer & Dependents data
            v
 [2. Invoice PDF Ingestion (invoices/)]
            |
            v
 [invoice_parser] -----> Creates invoices/<invoice_name>.json
            |
            v
 [is_invoice_already_in_f572?]
       |                                   |
    (YES: Duplicate)                   (NO: New Bill)
       |                                   |
       v                                   v
[Skip & Report "ALREADY_LOADED"]   [3. validate_deduction_eligibility] (CUIT Mod 11, CAE, Date, Dependents)
                                           |
                                           v
                                   [4. compute_deductions_engine] (RG 4003/17 Rates)
                                           |
                                           v
                                   [5. siradig_automator] (Loads items -> Saves Draft F.572)
```

---

## 4. Legal Matrix & Deduction Rules (ARCA RG 4003/17)

| Category Key (`siradig_code`) | Deduction Category | Requisitos Legales ARCA / Documentación | Porcentaje Deducible | Tope / Límite Aplicable |
| :--- | :--- | :--- | :--- | :--- |
| `MEDICO_PARAMEDICO` | **Gastos Médicos y Paramédicos** | Factura del profesional / clínica. CUIT prestador y CUIT beneficiario (titular o carga). | **40%** del neto no reintegrado | Hasta **5%** de Ganancia Neta Anual. |
| `CUOTA_MEDICO_ASSIST` | **Medicina Prepaga** | Comprobante de pago o factura de medicina prepaga. CUIT entidad. | **100%** de lo abonado | Hasta **5%** de Ganancia Neta Anual. |
| `GASTOS_EDUCACION` | **Gastos de Educación** | Factura de colegio, universidad o útiles/libros. CUIT entidad. Para hijos/as hasta 24 años. | **100%** de lo abonado | Hasta **40%** MNI Anual. |
| `ALQUILER_HABITACION` | **Alquiler Casa-Habitación** | Factura/recibo emitido por locador o inmobiliaria (CUIT). Contrato adjunto. | **40%** del total pagado | Menor entre 40% y 100% MNI. |
| `CASAS_PARTICULARES` | **Servicio Doméstico** | Recibo de sueldo + VEP de aportes y contribuciones ARCA (CUIT empleado). | **100%** de lo abonado | Hasta el **100%** MNI Anual. |

---

## 5. Security & Browser Guardrails

1. **Credentials Security**: Store credentials and dependent details in `.env` (protected by `.gitignore`).
2. **Draft Mode Only**: The agent ONLY clicks **"Guardar"** (`Borrador`). **NEVER** submits the form (`Enviar al Empleador`).
3. **Interactive Window**: Executed with `BROWSER_HEADLESS=false` so the user can inspect progress on screen inside Antigravity IDE.
