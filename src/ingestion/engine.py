from typing import List
from datetime import datetime, timezone
from fhir.client import FHIRClient
from .models import Fact, FactType
from .converter import entry_to_facts

class FactTableBuilder:
    def __init__(self, client: FHIRClient):
        self.client = client

    def build_fact_table(self, patient_id: str) -> List[Fact]:
        """
        Fetches all relevant resources for a patient and returns a sorted list of Facts.
        """
        facts = []
        
        # 1. Fetch Encounters
        # Note: In a real app, we'd wrap these in a try/except block or use asyncio
        enc_facts = []
        encounters = self.client.search_encounters(patient_id)
        for enc in encounters:
            # Wrap in specific structure for converter if needed, or update converter to take resource directly
            # The current converter expects "entry" structure occasionally if we used bundle iteration,
            # but here "encounters" is a list of resources.
            # Let's adjust converter usage or pass a mock entry wrapper.
            entry = {"resource": enc}
            enc_facts.extend(entry_to_facts(entry))
        facts.extend(enc_facts)

        # 2. Fetch Observations
        obs_facts = []
        # Lab
        labs = self.client.search_observations(patient_id, category="laboratory")
        for lab in labs:
            entry = {"resource": lab}
            obs_facts.extend(entry_to_facts(entry))
        # Vital
        vitals = self.client.search_observations(patient_id, category="vital-signs")
        for vital in vitals:
            entry = {"resource": vital}
            obs_facts.extend(entry_to_facts(entry))
        facts.extend(obs_facts)

        # 3. Fetch Meds
        med_facts = []
        meds = self.client.search_medication_requests(patient_id)
        for med in meds:
            entry = {"resource": med}
            med_facts.extend(entry_to_facts(entry))
        facts.extend(med_facts)
        
        # 4. Sort by Timestamp Descending
        facts.sort(key=lambda x: x.timestamp, reverse=True)
        
        # 5. Detect Gaps/Issues
        warnings = self.detect_gaps(facts)
        for w in warnings:
            # We insert warnings as special Facts for the LLM to see, or we could handle them separately.
            # For this MVP, let's append them as "System" facts.
            facts.insert(0, Fact(
                patient_id=patient_id,
                timestamp=datetime.now(timezone.utc),
                type=FactType.OTHER,
                name="Data Quality Warning",
                value=w,
                source_id="System"
            ))
            
        return facts

    def detect_gaps(self, facts: List[Fact]) -> List[str]:
        warnings = []
        # Example 1: Check if Med Orders have recent Med Admins (simplified)
        med_orders = [f for f in facts if f.type == FactType.MED_ORDER]
        med_admins = [f for f in facts if f.type == FactType.MED_ADMIN]
        
        if med_orders and not med_admins:
            warnings.append("Medication administrations are not retrieved by this prototype; administration status is unknown.")
            
        return warnings
