from pydantic import BaseModel, Field
from typing import Optional, List, TypeVar, Generic
import enum
from datetime import datetime

# --- Enums ---
class ProductTypeEnum(str, enum.Enum):
    """Defines the allowed product types."""
    INTEREST_PRODUCT = "InterestProduct"
    CHECKING_ACCOUNT = "CheckingAccount"
    SECURITY = "Security"

class RiskClassStrEnum(str, enum.Enum):
    """Defines the risk classes as string enums."""
    ONE = "1"
    TWO = "2"
    THREE = "3"
    FOUR = "4"
    FIVE = "5"

class RoleTypeEnum(str, enum.Enum):
    """Defines the allowed role types for employees."""
    ADVISOR = "Advisor"
    SERVICE = "Service"

# --- Atomic Fact Model ---
class ProvableFact(BaseModel):
    """
    A single, provable fact, consisting of the extracted value
    and the exact text snippet (evidence) that supports it.
    """
    value: str = Field(..., description="The extracted fact, e.g., 'Max Musterman' or 'Branch Buchholz'.")
    evidence: str = Field(..., description="The exact text snippet from the source that proves this fact.")

# --- Metadata Models ---
class ProvenanceModel(BaseModel):
    """
    Describes the origin (provenance) and timestamp (versioning)
    of a single extraction.
    """
    url: str
    retrieved_at: datetime = Field(default_factory=datetime.now)
    trust_score: float

T = TypeVar('T', bound=BaseModel)
class ExtractionPackage(BaseModel, Generic[T]):
    """
    A generic container that bundles the extracted payload (e.g., BranchData
    or KnowledgeGraphData) with its provenance metadata.
    This is the object passed to the ingestor.
    """
    metadata: ProvenanceModel
    data: T

class GrounderResponse(BaseModel):
    """The schema for the Grounder's simple boolean response."""
    is_grounded: bool

# --- Data Models (Ontology) ---
class EmployeeModel(BaseModel):
    """Describes a single employee."""
    name: ProvableFact
    email: Optional[ProvableFact] = None
    phone: Optional[ProvableFact] = None
    role_type: RoleTypeEnum = Field(..., description="Classify the employee's role as 'Advisor' or 'Service'.")

class BranchModel(BaseModel):
    """Describes a single bank branch."""
    name: ProvableFact
    address: Optional[ProvableFact] = None
    employees: List[EmployeeModel] = []

class BranchData(BaseModel):
    """The top-level schema for extracting branch information."""
    branch: BranchModel

class ConditionModel(BaseModel):
    """Describes a single financial condition."""
    type: Optional[ProvableFact] = None
    min_amount: Optional[int] = None
    max_amount: Optional[int] = None
    term_years: Optional[int] = None
    interest_rate: Optional[ProvableFact] = None

class FAQModel(BaseModel):
    """Describes a single Question-Answer pair."""
    question: ProvableFact
    answer: ProvableFact

class ProductModel(BaseModel):
    """Describes the core product."""
    name: ProvableFact
    description: Optional[ProvableFact] = None

class ProductTypeModel(BaseModel):
    """Describes the classified type of the product."""
    name: ProductTypeEnum

class RiskClassModel(BaseModel):
    """Describes the estimated risk class of the product."""
    risk_class: RiskClassStrEnum = Field(..., description="Estimate the product risk and select the appropriate class from '1' to '5'.")

    @property
    def class_as_integer(self) -> int:
        return int(self.risk_class.value)

class KnowledgeGraphData(BaseModel):
    """The top-level schema for extracting financial product information."""
    product: ProductModel
    product_type: ProductTypeModel
    risk_class: RiskClassModel
    conditions: Optional[List[ConditionModel]] = None
    faqs: Optional[List[FAQModel]] = None
