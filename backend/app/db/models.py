
from sqlalchemy import (Boolean, Column, DateTime, ForeignKey, Integer, String,
                        Text, UniqueConstraint)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class District(Base):
    """
    District model for representing administrative districts in the system.

    This model stores information about different districts including their
    names and unique district IDs.
    """

    __tablename__ = "districts"

    id = Column(Integer, primary_key=True)
    dist_name = Column(Text, nullable=False)
    dist_id = Column(Integer, nullable=False, unique=True)

    __table_args__ = (UniqueConstraint("dist_id", name="dist_id_uniq"),)


class Complaint(Base):
    """
    Represents a complaint record with details about the petitioner, complaint status, assignment, and categorization.

    This model stores information about a complaint, including the petitioner's details, the nature of the grievance,
    the status of the complaint, and the various stages of the complaint process.

    Attributes:
        id (int): A unique identifier for each complaint (primary key)
        ticket_no (str): A unique ticket number for each complaint
        petitioner_name (str): The name of the person filing the complaint
        petitioner_mobile (str): The mobile number of the petitioner
        petitioner_email (str): The email address of the petitioner
        grievance (str): A description of the complaint
        document_url (str): Url to access the pdf document related to the complaint.
        office (str): The office where the complaint was received
        received_by (str): The name or identifier of the person who received the complaint
        district (str): The district associated with the complaint
        block (str): The block or sub-region within the district
        address (str): The address of the petitioner or complaint location
        mode (str): The mode through which the complaint was received (e.g., online, in-person)
        disability (str): The disability status of the petitioner, if applicable
        status (str): The current status of the complaint
        govt_ticket (bool): Indicates if the ticket is a government ticket
        created_on (datetime): The date and time when the complaint was created
        tagged_to (str): The entity or person to whom the complaint is tagged
        tagged_by (str): The entity or person who tagged the complaint
        tagged_date (datetime): The date and time when the complaint was tagged
        category (str): The main category of the complaint
        dept (str): The department associated with the complaint
        subcategory (str): The subcategory of the complaint
        state (str): The state associated with the complaint
        petitioner_gender (str): The gender of the petitioner
        transfer_status (str): The status of complaint transfer, if applicable
        urgent (str): Indicates if the complaint is marked as urgent
        pending_with (str): The person or entity currently handling the complaint
        assigned_on (datetime): The date and time when the complaint was assigned
        escalation_date (datetime): The date and time for escalation, if set
        self_assign (str): Indicates if the complaint was self-assigned
        resolved_on (datetime): The date and time when the complaint was resolved
        benefitted (str): Indicates if the petitioner benefitted from the complaint resolution
        local_document_path (str): Local path where the document is storage
        document_downloaded (bool): Indicates if the document has been downloaded
        document_download_date (datetime): Indicates the date in which the document has been downloaded
        document_download_error (str): Captures the error obtained when failing to download the document
    """

    __tablename__ = "complaints"

    id = Column(Integer, primary_key=True)
    ticket_no = Column(String(50), unique=True, nullable=False)
    petitioner_name = Column(Text, nullable=True)
    petitioner_mobile = Column(String(20), nullable=True)
    petitioner_email = Column(String(100), nullable=True)
    grievance = Column(Text, nullable=True)
    document_url = Column(Text, nullable=True)
    office_id = Column(Integer, nullable=False)
    office = Column(Text, nullable=True)
    received_by = Column(Text, nullable=True)
    district_id = Column(Integer, nullable=True)
    district = Column(Text, nullable=True)
    block_id = Column(Integer, nullable=False)
    block = Column(Text, nullable=True)
    address = Column(Text, nullable=True)
    mode = Column(Text, nullable=True)
    disability = Column(Text, nullable=True)
    status = Column(Text, nullable=True)
    govt_ticket = Column(Boolean, nullable=True)
    created_on = Column(DateTime, nullable=True)
    tagged_to = Column(Text, nullable=True)
    tagged_by = Column(Text, nullable=True)
    tagged_date = Column(DateTime, nullable=True)
    category_id = Column(Integer, nullable=False)
    category = Column(Text, nullable=True)
    dept_id = Column(Integer, nullable=False)
    dept = Column(Text, nullable=True)
    subcategory_id = Column(Integer, nullable=True)
    subcategory = Column(Text, nullable=True)
    state = Column(Text, nullable=True)
    petitioner_gender = Column(Text, nullable=False)
    transfer_status = Column(Text, nullable=False)
    urgent = Column(Text, nullable=False)
    pending_with = Column(Text, nullable=True)
    assigned_on = Column(DateTime, nullable=True)
    escalation_date = Column(DateTime, nullable=True)
    self_assign = Column(Text, nullable=False)
    resolved_by = Column(String, nullable=False)
    resolved_on = Column(DateTime, nullable=True)
    benefitted = Column(String, nullable=True)
    local_document_path = Column(Text, nullable=True)
    document_downloaded = Column(Boolean, default=False)
    document_download_date = Column(DateTime, nullable=True)
    document_download_error = Column(Text, nullable=True)
    trackingId = Column(String, nullable=True)

    __table_args__ = (UniqueConstraint("ticket_no", name="ticket_no_uniq"),)


class ActionHistory(Base):
    """
    Represents an action history record with details about the action taken on a complaint.

    Attributes:
        id (int): A unique identifier for each action history record
        complaint_id (int): The ID of the complaint associated with this action history
        action_type (str): The type of action taken (e.g., "Assigned", "Resolved", etc.)
        action_taken_date (datetime): The date and time when the action was taken
        action_taken_by (str): The name or identifier of the person who took the action
        action_status (str): The status of the action (e.g., "Pending", "Completed", etc.)
        action_taken_remark (str): Additional remarks or comments about the action
        complaint_status_with_authority (str): The status of the complaint with the authority
    """

    __tablename__ = "action_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticket_no = Column(String(50), ForeignKey("complaints.ticket_no"))
    complaint = relationship("Complaint", backref="action_history")
    action_taken_date = Column(DateTime, nullable=True)
    action_taken_by = Column(String(100), nullable=False)
    action_status = Column(Text, nullable=False)
    action_taken_remark = Column(Text, nullable=True)
    complaint_status_with_authority = Column(Text, nullable=False)
    trackingId = Column(String, nullable=True)


class APIRequestTracking(Base):
    """Track which API request combinations have been successfully processed."""

    __tablename__ = "api_request_tracking"

    id = Column(Integer, primary_key=True)
    year = Column(Integer, nullable=False)
    dist_id = Column(Integer, nullable=False)
    status = Column(Integer, nullable=False)
    office = Column(Integer, nullable=False)
    last_successful_fetch = Column(DateTime, nullable=True)
    records_count = Column(Integer, nullable=True)
    failure_count = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint(
            "year", "dist_id", "status", "office", name="api_request_uniq"
        ),
    )


class ActionHistoryAPIRequestTracking(Base):
    """Track which action history API request combinations have been successfully processed."""

    __tablename__ = "action_history_api_request_tracking"

    id = Column(Integer, primary_key=True)
    ticket_no = Column(String, ForeignKey("complaints.ticket_no"))
    complaint = relationship("Complaint", backref="action_history_api_request_tracking")
    last_successful_fetch = Column(DateTime, nullable=True)
    records_count = Column(Integer, nullable=True)
    failure_count = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("ticket_no", name="action_history_api_request_uniq"),
    )
