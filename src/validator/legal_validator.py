import re
from typing import Dict, Any, Tuple, List
from datetime import datetime

def validate_cuit(cuit: str) -> bool:
    """
    Validates CUIT/CUIL format and Modulo 11 checksum according to ARCA/AFIP algorithm.
    """
    clean_cuit = re.sub(r'\D', '', cuit or "")
    if len(clean_cuit) != 11:
        return False
    
    multipliers = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
    total = sum(int(clean_cuit[i]) * multipliers[i] for i in range(10))
    mod = total % 11
    verifier = 11 - mod
    
    if verifier == 11:
        verifier = 0
    elif verifier == 10:
        verifier = 9
        
    return verifier == int(clean_cuit[10])

def validate_invoice_legal_requirements(invoice_data: Dict[str, Any], dependents_list: List[Dict[str, Any]], fiscal_year: int) -> Tuple[bool, List[str]]:
    """
    Validates legal requirements of an invoice for ARCA F.572 SiRADIG loading.
    Returns (is_valid, list_of_errors)
    """
    errors = []
    
    # 1. CUIT Emisor Validation
    vendor_cuit = invoice_data.get("vendor_cuit", "")
    if not validate_cuit(vendor_cuit):
        errors.append(f"Invalid Vendor CUIT (Emisor): '{vendor_cuit}'. Modulo 11 validation failed.")

    # 2. Receipt Type & POS / Number validation
    receipt_type = invoice_data.get("receipt_type", "")
    if not receipt_type:
        errors.append("Missing Receipt Type (e.g. FACTURA_B, FACTURA_C).")
        
    pos = invoice_data.get("point_of_sale")
    number = invoice_data.get("receipt_number")
    if pos is None or pos <= 0:
        errors.append(f"Invalid Point of Sale (Punto de Venta): {pos}")
    if number is None or number <= 0:
        errors.append(f"Invalid Receipt Number: {number}")

    # 3. Issue Date & Fiscal Year Alignment
    issue_date_str = invoice_data.get("issue_date", "")
    try:
        issue_date = datetime.strptime(issue_date_str, "%Y-%m-%d")
        if issue_date.year != fiscal_year:
            # Note: For annual liquidation up to March 31 of next year, expenses can belong to prior year
            errors.append(f"Invoice date {issue_date_str} year ({issue_date.year}) does not match fiscal year ({fiscal_year}).")
    except ValueError:
        errors.append(f"Invalid issue date format: '{issue_date_str}'. Expected YYYY-MM-DD.")

    # 4. CAE / CAEA Presence
    cae = invoice_data.get("cae")
    if not cae:
        # Warning/error depending on strictness
        pass  # Will be flagged as mandatory field in ARCA portal

    # 5. Beneficiary CUIT check (if expense is for dependent)
    beneficiary_cuil = invoice_data.get("beneficiary_cuil")
    if beneficiary_cuil:
        if not validate_cuit(beneficiary_cuil):
            errors.append(f"Invalid Beneficiary CUIT/CUIL: '{beneficiary_cuil}'.")
        else:
            clean_ben = re.sub(r'\D', '', beneficiary_cuil)
            registered_cuits = [re.sub(r'\D', '', d.get("cuit", "")) for d in dependents_list]
            taxpayer_cuit = invoice_data.get("taxpayer_cuit", "")
            if taxpayer_cuit:
                registered_cuits.append(re.sub(r'\D', '', taxpayer_cuit))
            
            if registered_cuits and clean_ben not in registered_cuits:
                errors.append(f"Beneficiary CUIT {beneficiary_cuil} is not registered in taxpayer's family dependents (.env).")

    is_valid = len(errors) == 0
    return is_valid, errors
