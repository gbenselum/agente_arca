import os
from typing import List, Dict, Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class DependentConfig:
    def __init__(self, first_name: str, last_name: str, cuit: str, relationship: str, birth_date: str, percentage: int = 100):
        self.first_name = first_name
        self.last_name = last_name
        self.cuit = cuit
        self.relationship = relationship
        self.birth_date = birth_date
        self.percentage = percentage

    def to_dict(self) -> Dict:
        return {
            "first_name": self.first_name,
            "last_name": self.last_name,
            "cuit": self.cuit,
            "relationship": self.relationship,
            "birth_date": self.birth_date,
            "percentage": self.percentage
        }

class Settings:
    def __init__(self):
        self.arca_cuil: str = os.getenv("ARCA_CUIL", "")
        self.arca_clave_fiscal: str = os.getenv("ARCA_CLAVE_FISCAL", "")
        self.taxpayer_name: str = os.getenv("TAXPAYER_NAME", "")
        self.taxpayer_cuit: str = os.getenv("TAXPAYER_CUIT", os.getenv("ARCA_CUIL", ""))
        self.fiscal_year: int = int(os.getenv("FISCAL_YEAR", "2026"))
        self.browser_headless: bool = os.getenv("BROWSER_HEADLESS", "false").lower() == "true"
        self.browser_slowmo_ms: int = int(os.getenv("BROWSER_SLOWMO_MS", "500"))
        self.auto_save_draft: bool = os.getenv("AUTO_SAVE_DRAFT", "true").lower() == "true"
        self.dependents: List[DependentConfig] = self._load_dependents()

    def _load_dependents(self) -> List[DependentConfig]:
        dependents = []
        i = 1
        while True:
            first_name = os.getenv(f"DEPENDENT_{i}_FIRST_NAME")
            if not first_name:
                break
            last_name = os.getenv(f"DEPENDENT_{i}_LAST_NAME", "")
            cuit = os.getenv(f"DEPENDENT_{i}_CUIT", "")
            relationship = os.getenv(f"DEPENDENT_{i}_RELATIONSHIP", "HIJO")
            birth_date = os.getenv(f"DEPENDENT_{i}_BIRTH_DATE", "")
            percentage = int(os.getenv(f"DEPENDENT_{i}_PERCENTAGE", "100"))

            dependents.append(DependentConfig(
                first_name=first_name,
                last_name=last_name,
                cuit=cuit,
                relationship=relationship,
                birth_date=birth_date,
                percentage=percentage
            ))
            i += 1
        return dependents

settings = Settings()
