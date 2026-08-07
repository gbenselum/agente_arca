from typing import Dict, Any

CATEGORY_RATES = {
    "MEDICO_PARAMEDICO": 0.40,
    "CUOTA_MEDICO_ASSIST": 1.00,
    "GASTOS_EDUCACION": 1.00,
    "ALQUILER_HABITACION": 0.40,
    "ALQUILER_ADICIONAL_10": 0.10,
    "CASAS_PARTICULARES": 1.00,
    "INTERES_HIPOTECARIO": 1.00,
    "DONACIONES": 1.00,
    "SEGUROS_VIDA_RETIRO": 1.00,
    "GASTOS_SEPELIO": 1.00
}

def compute_deduction(invoice_data: Dict[str, Any], siradig_code: str) -> Dict[str, Any]:
    """
    Computes net deductible amount and rate based on RG 4003/17 rules.
    """
    total_amount = float(invoice_data.get("total_amount", 0.0))
    reimbursed_amount = float(invoice_data.get("reimbursed_amount", 0.0))
    
    net_out_of_pocket = max(0.0, total_amount - reimbursed_amount)
    rate = CATEGORY_RATES.get(siradig_code, 1.00)
    computable_deduction = net_out_of_pocket * rate
    
    return {
        "invoice_id": invoice_data.get("invoice_id", "INV-UNKNOWN"),
        "siradig_code": siradig_code,
        "gross_amount": total_amount,
        "reimbursed_amount": reimbursed_amount,
        "net_out_of_pocket": net_out_of_pocket,
        "deductible_rate": rate,
        "computable_deduction": round(computable_deduction, 2),
        "requires_employer_cap_check": True
    }
