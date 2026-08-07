# Skill: ARCA SiRADIG F.572 Web Automation & Invoice Processing Agent

## 1. System Overview & Purpose

This skill definition equips an AI Agent (integrated via Model Context Protocol - MCP) to validate, categorize, and structure deduction data for Argentina's **Impuesto a las Ganancias (4ta Categoría - Trabajadores en Relación de Dependencia)**. 

The agent operates as a tax assistant that receives invoice/receipt metadata (via OCR or document ingestion), validates compliance with **ARCA** (Agencia de Recaudación y Control Aduanero, ex-AFIP) rules under Resolution **RG 4003/17** and modifications, calculates deductible amounts, and formats JSON payloads ready for transmission or manual load into **SiRADIG - Formulario 572 Web**.

---

## 2. Tax Domain Rules & Deductions Matrix

The agent must evaluate all incoming receipts against the following regulatory criteria before approval:

| Deduction Category | Subcategory / Description | Deductible Percentage | Applicable Limit / Cap | System Key (`siradig_code`) |
| :--- | :--- | :--- | :--- | :--- |
| **Gastos Médicos y Paramédicos** | Fonoaudiología, odontología, medicina general, kinesiología, psicología, etc. | **40%** del neto no reintegrado ($Importe - Reintegro$) | Hasta el **5%** de la Ganancia Neta Anual. | `MEDICO_PARAMEDICO` |
| **Medicina Prepaga / Cuotas** | Aportes a prepagas u obras sociales (no descontados en el recibo de sueldo). | **100%** de lo abonado | Hasta el **5%** de la Ganancia Neta Anual. | `CUOTA_MEDICO_ASSIST` |
| **Alquiler Casa-Habitación** | Contrato de alquiler de vivienda única (Locatario). | **40%** del total pagado | Menor entre el 40% y el 100% del MNI (Mínimo No Imponible). | `ALQUILER_HABITACION` |
| **Alquiler Adicional (Ley 27.737)** | Adicional por contrato registrado en RELI (Locatario y Locador). | **10%** del valor anual | Sin límite anual. | `ALQUILER_ADICIONAL_10` |
| **Servicio Doméstico** | Remuneraciones y contribuciones patronales (Casas Particulares). | **100%** de lo abonado | Hasta el **100%** del MNI anual. | `CASAS_PARTICULARES` |
| **Gastos de Educación** | Servicios/herramientas educativas para cargas de familia (hasta 24 años). | **100%** de lo abonado | Hasta el **40%** del MNI anual. | `GASTOS_EDUCACION` |
| **Intereses Hipotecarios** | Compra/construcción de vivienda única. | **100%** de los intereses | **$20.000 ARS** anuales. | `INTERES_HIPOTECARIO` |
| **Donaciones** | Entidades exentas reconocidas por ARCA (art. 81 Ley de Ganancias). | **100%** de lo donado | Hasta el **5%** de la Ganancia Neta Anual. | `DONACIONES` |
| **Seguros de Vida / Retiro** | Primas por seguros para caso de muerte o retiro privado. | **100%** de lo abonado | Tope fijado anualmente por norma reglamentaria. | `SEGUROS_VIDA_RETIRO` |
| **Gastos de Sepelio** | Por fallecimiento de cargas de familia. | **100%** de lo pagado | **$996,23 ARS** por año. | `GASTOS_SEPELIO` |

---

## 3. Data Schema Specifications

### 3.1 Carga de Familia Entity (`family_dependents`)
```json
{
  "dependent_id": "DEP-001",
  "cuil": "20456789019",
  "first_name": "Juan",
  "last_name": "Pérez",
  "relationship": "HIJO",
  "birth_date": "2018-05-14",
  "is_incapacitated_for_work": false,
  "percentage_computed": 100
}
```

### 3.2 Invoice Processing Input (`invoice_input`)
```json
{
  "invoice_id": "INV-2026-0089",
  "vendor_cuit": "30711234567",
  "vendor_name": "Centro Fonoaudiológico S.A.",
  "receipt_type": "FACTURA_B",
  "point_of_sale": 4,
  "receipt_number": 12890,
  "issue_date": "2026-03-15",
  "total_amount": 45000.00,
  "reimbursed_amount": 10000.00,
  "concept_description": "Tratamiento fonoaudiológico mes de Marzo - Beneficiario: Juan Pérez",
  "beneficiary_cuil": "20456789019",
  "suggested_category": "GASTOS_MEDICOS"
}
```

---

## 4. MCP Tools Interface Definition

To execute this skill, the AI agent relies on the following MCP tool specifications:

### Tool 1: `parse_and_extract_invoice`
Extracts structured tax details from OCR text or document images.
* **Inputs:** `raw_text` (string) OR `file_path` (string).
* **Outputs:** Structured JSON matching `invoice_input`.

### Tool 2: `validate_deduction_eligibility`
Verifies tax parameters before computing deductible amounts.
* **Inputs:** `invoice_data` (JSON), `taxpayer_data` (JSON).
* **Validation Logic:**
  1. CUIT format check (modulo 11 algorithm).
  2. Fiscal year alignment (e.g., invoice date in 2026 maps to period 2026).
  3. Validate beneficiary against registered `family_dependents` (must be under 18 or incapacitated if `relationship` is `HIJO`).
  4. Ensure receipt type is valid (B or C for final consumer).

### Tool 3: `compute_deductions_engine`
Calculates net deductible amount and applies category specific formulas.
* **Mathematical Formula for Medical Expenses (MEDICO_PARAMEDICO):**
  Net Payable = Total Amount - Reimbursed Amount
  Deductible Base = Net Payable * 0.40
* **Output:**
  ```json
  {
    "invoice_id": "INV-2026-0089",
    "siradig_code": "MEDICO_PARAMEDICO",
    "gross_amount": 45000.00,
    "reimbursed_amount": 10000.00,
    "net_out_of_pocket": 35000.00,
    "deductible_rate": 0.40,
    "computable_deduction": 14000.00,
    "requires_employer_cap_check": true,
    "cap_type": "PERCENTAGE_NET_INCOME_5"
  }
  ```

### Tool 4: `generate_siradig_payload`
Compiles all validated deductions for the specified fiscal year into the standard JSON format for SiRADIG F.572 Web.
* **Inputs:** `taxpayer_cuit` (string), `fiscal_year` (integer), `deductions_list` (array of objects).

---

## 5. Execution Flow & Guardrails

```
[Invoice/Receipt Ingestion]
           |
           v
[Tool: parse_and_extract_invoice]
           |
           v
[Tool: validate_deduction_eligibility] ---- (Invalid CUIT / Exceeded Age) ---> [Reject & Alert User]
           | (Valid)
           v
[Tool: compute_deductions_engine]
           |
           v
[Tool: generate_siradig_payload]
```

### Agent Guardrails & Strict Rules
1. **Zero Estimation:** The agent MUST NOT guess or estimate reimbursed amounts. If unstated, it must prompt the user or set `reimbursed_amount = 0.00`.
2. **Medicines Rule:** Standalone pharmacy invoices for medication are **NOT deductible** unless part of a clinical hospitalization stay.
3. **Double Deduction Prevention:** If an expense (e.g., prepaga) is deducted directly on the payroll pay stub (*recibo de sueldo*), it MUST NOT be declared again via SiRADIG.
4. **Cap Responsibility Division:**
   * **Worker/Agent Responsibility:** Calculate the exact out-of-pocket net base and deductible percentage (e.g., 40% for medical, 100% for education).
   * **Employer/ARCA System Responsibility:** Apply the final annual capped caps (5% net income limit or MNI annual cap) during the final liquidation (*liquidación anual*).
