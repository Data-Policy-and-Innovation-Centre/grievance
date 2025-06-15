from pydantic import BaseModel, field_validator, Field
from typing import Optional, Any
from loguru import logger
from datetime import datetime
from . import OFFICE
from difflib import get_close_matches
from app.config import settings

class District(BaseModel):
    """
    Pydantic model representing a district with its name and unique identifier.

    Attributes:
        distName (str): The name of the district.
        distId (int): The unique identifier for the district.
    """
    dist_name: str = Field(..., alias="distName")
    dist_id: int = Field(..., alias="distId")

class Complaint(BaseModel):
    """
    Represents a complaint record with details about the petitioner, complaint status, assignment, and categorization.

    Attributes:
        ticket_no (str): Unique identifier for the complaint ticket.
        petitioner_name (Optional[str]): Name of the person filing the complaint.
        petitioner_mobile (Optional[str]): Mobile number of the petitioner.
        petitioner_email (Optional[str]): Email address of the petitioner.
        grievance: (str): Description of the grievance or complaint.
        office (str): Office where the complaint was received.
        received_by (str): Name or identifier of the person who received the complaint.
        district (str): District associated with the complaint.
        block (Optional[str]): Block or sub-region within the district.
        address (Optional[str]): Address of the petitioner or complaint location.
        mode (str): Mode through which the complaint was received (e.g., online, in-person).
        disability (Optional[str]): Disability status of the petitioner, if applicable.
        status (str): Current status of the complaint (e.g., pending, resolved).
        govt_ticket (bool): Indicates if the ticket is a government ticket.
        created_on (datetime): Date and time when the complaint was created.
        tagged_to (Optional[Any]): Entity or person to whom the complaint is tagged.
        tagged_by (Optional[Any]): Entity or person who tagged the complaint.
        tagged_date (Optional[datetime]): Date and time when the complaint was tagged.
        category (str): Main category of the complaint.
        dept (Optional[str]): Department associated with the complaint.
        subcategory (Optional[str]): Subcategory of the complaint.
        state (str): State associated with the complaint.
        petitioner_gender (str): Gender of the petitioner.
        transfer_status (str): Status of complaint transfer, if applicable.
        urgent (str): Indicates if the complaint is marked as urgent.
        pending_with (Optional[str]): Person or entity currently handling the complaint.
        assigned_on (datetime): Date and time when the complaint was assigned.
        escalation_date (Optional[datetime]): Date and time for escalation, if set.
        self_assign (Optional[str]): Indicates if the complaint was self-assigned.
        resolved_on (Optional[datetime]): Date and time when the complaint was resolved.
        benefitted (Optional[str]): Indicates if the petitioner benefitted from the resolution.
    """
    ticket_no: str = Field(..., alias="ticketNumber")
    petitioner_name: Optional[str] = Field(..., alias="petitionerName")
    petitioner_mobile: Optional[str] = Field(..., alias="petitionerMobile")
    petitioner_email: Optional[str] = Field(..., alias="petitionerEmail")
    grievance: str = Field(..., alias="grievanceSubject")
    office: str = Field(..., alias="officeNAme")
    received_by: str = Field(..., alias="RecievedByOfficerName")
    district: str = Field(..., alias="districtName")
    block: Optional[str] = Field(..., alias="blockName")
    address: Optional[str] = Field(..., alias="Address")
    mode: str = Field(..., alias="modeName")
    disability: Optional[str] = Field(..., alias="disbilityName")
    status: str = Field(..., alias="StatusName")
    govt_ticket: bool = Field(..., alias="govtTicket")
    created_on: datetime = Field(..., alias="CreatedOn")
    tagged_to: Optional[Any] = Field(..., alias="taggedTo")
    tagged_by: Optional[Any] = Field(..., alias="taggedByName")
    tagged_date: Optional[datetime] = Field(..., alias="taggedDate")
    category: str = Field(..., alias="category")
    dept: Optional[str] = Field(..., alias="deptName")
    subcategory: Optional[str] = Field(..., alias="Subcategory")
    state: str = Field(..., alias="stateName")
    petitioner_gender: str = Field(..., alias="genderName")
    transfer_status: str = Field(..., alias="transferStatus")
    urgent: str = Field(..., alias="mostUrgent")
    pending_with: Optional[str] = Field(..., alias="pendingwithName")
    assigned_on: datetime = Field(..., alias="assignedOn")
    escalation_date: Optional[datetime] = Field(..., alias="escalationDate")
    self_assign: Optional[str] = Field(..., alias="isSelfAssign")
    resolved_on: Optional[datetime] = Field(..., alias="ResolvedOn")
    benefitted: Optional[str] = Field(..., alias="benefitted")

    @field_validator("office", mode="before")
    def validate_office(cls, v):
        if v not in OFFICE:
            closest = get_close_matches(str(v), OFFICE.values(), n=1)
            if closest:
                return closest[0]
            raise ValueError(f"Office '{v}' is not recognized and no close match found.")
        return v
    
    @field_validator("govt_ticket", mode="before")
    def validate_govt_ticket(cls, v):
        if v in ["Yes", "yes"]:
            return True
        elif v in ["No", "no"]:
            return False
        else:
            raise ValueError(f"Government ticket status '{v}' is not recognized.")
        
    @field_validator("created_on", "tagged_date", "assigned_on", "escalation_date", "resolved_on", mode="before")
    def validate_datetime(cls, v):
        if v is None:
            return None
        if isinstance(v, datetime):
            return v
        try:
            return datetime.fromisoformat(v)
        except (ValueError, TypeError):
            try:
                return datetime.strptime(v, "%Y-%m-%dT%H:%M:%S")
            except (ValueError, TypeError):
                return None
            
class ActionHistory(BaseModel):
    """
    Represents an action taken on a complaint, including the action taken by, the date of action, the remarks, and the status of the action.

    Attributes:
        ticket_no (str): The ticket number associated with the complaint.
        action_taken_by (str): The name of the person who took the action.
        action_taken_date (datetime): The date on which the action was taken.
        action_taken_remark (str): The remarks made by the person who took the action.
        action_status (str): The status of the action taken.
        complaint_status_with_authority (str): The status of the complaint with the authority.
    """
    ticket_no: str = Field(..., alias="ticketNumber")
    action_taken_by: str
    action_taken_date: Optional[datetime]
    action_taken_remark: str
    action_status: str
    complaint_status_with_authority: str

    @field_validator("action_taken_date", mode="before")
    def validate_datetime(cls, v):
        if v is None:
            return None
        if isinstance(v, datetime):
            return v
        try:
            return datetime.fromisoformat(v)
        except (ValueError, TypeError):
            try:
                return datetime.strptime(v, "%Y-%m-%dT%H:%M:%S")
            except (ValueError, TypeError):
                return None
        

def validate(items: list[dict], model: BaseModel) -> list[BaseModel]:
    """
    Validates data against a Pydantic model.
    Args:
        items (list[dict]): The data to validate.
        model (BaseModel): The Pydantic model to validate against.
    Returns:
        list[BaseModel]: The validated data.
    Raises:
        ValueError: If the data does not match the expected format.
    """
    
    logger.info(f"Validating {len(items)} {model.__name__} records")
    validated = []
    errors = []
    for idx, item in enumerate(items):
        try:
            validated.append(model(**item))
        except Exception as e:
            errors.append((idx, item, str(e)))
    if errors:
        error_msgs = "\n".join(
            [f"Index {idx}: {err}" for idx, itm, err in errors]
        )
        logger.error(f"Validation failed for {len(errors)} records. Errors:\n{error_msgs}")
    return validated

def validate_action_history(items: list[dict], ticket_no: str) -> list[ActionHistory]:
    """
    Validates action history data against the ActionHistory model.

    Args:
        items (list[dict]): The action history data to validate.
        ticket_no (str): The ticket number to associate with each action history record.

    Returns:
        list[ActionHistory]: The validated data.
    """
    for item in items:
        item["ticketNumber"] = ticket_no
    return validate(items, ActionHistory)

