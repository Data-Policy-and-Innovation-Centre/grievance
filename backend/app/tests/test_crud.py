from datetime import datetime

import asyncio
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.db.crud import (batch_create_action_history,
                         batch_create_or_update_complaints,
                         batch_create_or_update_districts,
                         bulk_load_action_histories, bulk_load_complaints,
                         bulk_load_districts, create_action_history,
                         create_or_update_complaint, create_or_update_district,
                         get_action_history_by_ticket, get_all_districts,
                         get_complaint_by_ticket, get_complaints_by_district,
                         get_complaints_by_status,
                         get_complaints_without_documents, get_district_by_id,
                         get_district_by_name, update_document_status)
from app.db.models import (ActionHistory, ActionHistoryAPIRequestTracking,
                           APIRequestTracking, Base, Complaint, District)
from app.ingestion.schemas import ActionHistory as ActionHistorySchema
from app.ingestion.schemas import Complaint as ComplaintSchema
from app.ingestion.schemas import District as DistrictSchema


@pytest.fixture(autouse=True)
def setup_test_environment():
    """
    Set up the test environment for CRUD tests.
    This ensures we use the real OFFICE constant for these tests.
    """
    import sys

    from app.ingestion import OFFICE as REAL_OFFICE
    from app.ingestion import schemas

    # Store the original OFFICE if it exists
    original_office = getattr(schemas, "OFFICE", None)

    # Set the real OFFICE constant
    sys.modules["app.ingestion.schemas"].OFFICE = REAL_OFFICE

    yield

    # Restore the original OFFICE if it existed
    if original_office is not None:
        sys.modules["app.ingestion.schemas"].OFFICE = original_office
    elif hasattr(schemas, "OFFICE"):
        delattr(schemas, "OFFICE")


# Test database setup
@pytest_asyncio.fixture(scope="function")
async def db_session():
    """Create a fresh database for each test."""
    # Create in-memory SQLite database for testing
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create a new session for the test
    TestingAsyncSessionLocal = sessionmaker(bind = engine, class_=AsyncSession, expire_on_commit=False)

    async with TestingAsyncSessionLocal() as session:
        yield session 


# Test data fixtures
@pytest.fixture
def sample_district_data():
    return DistrictSchema(distName="Test District", distId=1)


@pytest.fixture
def sample_complaint_data():
    return ComplaintSchema(
        ticketNumber="T123",
        petitionerName="John Doe",
        petitionerMobile="1234567890",
        petitionerEmail="john@example.com",
        grievanceSubject="Test Grievance",
        Document="example.pdf",
        officeNAme="Cheif Minister",
        RecievedByOfficerName="Officer X",
        districtName="Test District",
        blockName="Test Block",
        Address="123 Test St",
        modeName="Online",
        disbilityName=None,
        StatusName="Pending",
        govtTicket="Yes",
        CreatedOn="2024-03-20T10:00:00",
        taggedTo=None,
        taggedByName=None,
        taggedDate=None,
        category="Test Category",
        deptName="Test Dept",
        Subcategory="Test Subcategory",
        stateName="Test State",
        genderName="Male",
        transferStatus="None",
        mostUrgent="No",
        pendingwithName=None,
        assignedOn="2024-03-20T10:00:00",
        escalationDate=None,
        isSelfAssign=None,
        ResolvedOn=None,
        benefitted=None,
    )


@pytest.fixture
def sample_action_history_data():
    return ActionHistorySchema(
        ticketNumber="T123",
        action_taken_by="Officer X",
        action_taken_date="2024-03-20T10:00:00",
        action_taken_remark="Test action",
        action_status="Completed",
        complaint_status_with_authority="Pending",
    )


# District CRUD tests
@pytest.mark.asyncio
async def test_create_district(db_session, sample_district_data):
    """Test creating a new district."""
    district = await create_or_update_district(db_session, sample_district_data)
    assert district.dist_id == 1
    assert district.dist_name == "Test District"

@pytest.mark.asyncio
async def test_get_district_by_id(db_session, sample_district_data):
    """Test retrieving a district by ID."""
    # First create a district
    await create_or_update_district(db_session, sample_district_data)

    # Then retrieve it
    district = await get_district_by_id(db_session, 1)
    assert district is not None
    assert district.dist_name == "Test District"


@pytest.mark.asyncio
async def test_get_district_by_name(db_session, sample_district_data):
    """Test retrieving a district by name."""
    # First create a district
    await create_or_update_district(db_session, sample_district_data)

    # Then retrieve it
    district = await get_district_by_name(db_session, "Test District")
    assert district is not None
    assert district.dist_id == 1


@pytest.mark.asyncio
async def test_update_district(db_session, sample_district_data):
    """Test updating an existing district."""
    # First create a district
    await create_or_update_district(db_session, sample_district_data)

    # Update the district
    updated_data = DistrictSchema(distName="Updated District", distId=1)
    updated_district = await create_or_update_district(db_session, updated_data)

    assert updated_district.dist_name == "Updated District"
    assert updated_district.dist_id == 1


@pytest.mark.asyncio
async def test_get_all_districts(db_session, sample_district_data):
    """Test retrieving all districts."""
    # Create multiple districts
    district1 = await create_or_update_district(db_session, sample_district_data)
    district2 = await create_or_update_district(
        db_session, DistrictSchema(distName="Test District 2", distId=2)
    )

    districts = await get_all_districts(db_session)
    assert len(districts) == 2
    assert districts[0].dist_name == "Test District"
    assert districts[1].dist_name == "Test District 2"


# Complaint CRUD tests
def test_create_complaint(db_session, sample_complaint_data):
    """Test creating a new complaint."""
    complaint = create_or_update_complaint(db_session, sample_complaint_data)
    assert complaint.ticket_no == "T123"
    assert complaint.petitioner_name == "John Doe"
    assert complaint.office == "Office of Chief Minister"


def test_get_complaint_by_ticket(db_session, sample_complaint_data):
    """Test retrieving a complaint by ticket number."""
    # First create a complaint
    create_or_update_complaint(db_session, sample_complaint_data)

    # Then retrieve it
    complaint = get_complaint_by_ticket(db_session, "T123")
    assert complaint is not None
    assert complaint.petitioner_name == "John Doe"
    assert complaint.office == "Office of Chief Minister"


def test_update_complaint(db_session, sample_complaint_data):
    """Test updating an existing complaint."""
    # First create a complaint
    create_or_update_complaint(db_session, sample_complaint_data)

    # Update the complaint
    updated_data = sample_complaint_data.model_copy(
        update={"petitioner_name": "Jane Doe"}
    )
    updated_complaint = create_or_update_complaint(db_session, updated_data)

    assert updated_complaint.petitioner_name == "Jane Doe"
    assert updated_complaint.ticket_no == "T123"


def test_get_complaints_by_district(db_session, sample_complaint_data):
    """Test retrieving complaints by district."""
    # Create multiple complaints
    create_or_update_complaint(db_session, sample_complaint_data)
    complaint2 = sample_complaint_data.model_copy(update={"ticket_no": "T124"})
    create_or_update_complaint(db_session, complaint2)

    complaints = get_complaints_by_district(db_session, "Test District")
    assert len(complaints) == 2


def test_get_complaints_by_status(db_session, sample_complaint_data):
    """Test retrieving complaints by status."""
    # Create a complaint
    create_or_update_complaint(db_session, sample_complaint_data)

    complaints = get_complaints_by_status(db_session, "Pending")
    assert len(complaints) == 1
    assert complaints[0].ticket_no == "T123"


# Action History CRUD tests
def test_create_action_history(db_session, sample_action_history_data):
    """Test creating a new action history record."""
    action = create_action_history(db_session, sample_action_history_data)
    assert action.ticket_no == "T123"
    assert action.action_taken_by == "Officer X"


def test_get_action_history_by_ticket(db_session, sample_action_history_data):
    """Test retrieving action history by ticket number."""
    # First create an action history record
    create_action_history(db_session, sample_action_history_data)

    # Then retrieve it
    actions = get_action_history_by_ticket(db_session, "T123")
    assert len(actions) == 1
    assert actions[0].action_taken_by == "Officer X"


# Batch operations tests
def test_batch_create_districts(db_session):
    """Test batch creating districts."""
    districts_data = [
        DistrictSchema(distName="District 1", distId=1),
        DistrictSchema(distName="District 2", distId=2),
        DistrictSchema(distName="District 3", distId=3),
    ]

    districts = batch_create_or_update_districts(db_session, districts_data)
    assert len(districts) == 3
    assert districts[0].dist_name == "District 1"
    assert districts[1].dist_name == "District 2"
    assert districts[2].dist_name == "District 3"


def test_batch_create_complaints(db_session, sample_complaint_data):
    """Test batch creating complaints."""
    complaints_data = [
        sample_complaint_data,
        sample_complaint_data.model_copy(deep=True, update={"ticket_no": "T124"}),
        sample_complaint_data.model_copy(deep=True, update={"ticket_no": "T125"}),
    ]

    complaints = batch_create_or_update_complaints(db_session, complaints_data)
    assert len(complaints) == 3
    assert complaints[0].ticket_no == "T123"
    assert complaints[1].ticket_no == "T124"
    assert complaints[2].ticket_no == "T125"


def test_batch_create_action_history(db_session, sample_action_history_data):
    """Test batch creating action history records."""
    actions_data = [
        sample_action_history_data,
        sample_action_history_data.model_copy(
            deep=True, update={"action_taken_remark": "Second action"}
        ),
        sample_action_history_data.model_copy(
            deep=True, update={"action_taken_remark": "Third action"}
        ),
    ]
    print(actions_data)
    actions = batch_create_action_history(db_session, actions_data)
    print(actions)
    assert len(actions) == 3
    assert actions[0].action_taken_remark == "Test action"
    assert actions[1].action_taken_remark == "Second action"
    assert actions[2].action_taken_remark == "Third action"


def test_bulk_load_districts(db_session):
    """Test bulk loading districts."""
    districts_data = [
        DistrictSchema(distName="Bulk District 1", distId=10),
        DistrictSchema(distName="Bulk District 2", distId=11),
        DistrictSchema(distName="Bulk District 3", distId=12),
    ]
    count = len(bulk_load_districts(db_session, districts_data))
    assert count == 3
    # Check that the districts are in the database
    all_districts = get_all_districts(db_session)
    names = [d.dist_name for d in all_districts]
    assert "Bulk District 1" in names
    assert "Bulk District 2" in names
    assert "Bulk District 3" in names


def test_bulk_load_complaints(db_session, sample_complaint_data):
    """Test bulk loading complaints."""
    complaints_data = [
        sample_complaint_data,
        sample_complaint_data.model_copy(deep=True, update={"ticket_no": "T200"}),
        sample_complaint_data.model_copy(deep=True, update={"ticket_no": "T201"}),
    ]
    count = len(bulk_load_complaints(db_session, complaints_data))
    assert count == 3
    # Check that the complaints are in the database
    tickets = [c.ticket_no for c in db_session.query(Complaint).all()]
    assert "T123" in tickets
    assert "T200" in tickets
    assert "T201" in tickets


def test_bulk_load_action_histories(db_session, sample_action_history_data):
    """Test bulk loading action histories."""
    actions_data = [
        sample_action_history_data,
        sample_action_history_data.model_copy(
            deep=True, update={"action_taken_remark": "Bulk second action"}
        ),
        sample_action_history_data.model_copy(
            deep=True, update={"action_taken_remark": "Bulk third action"}
        ),
    ]
    count = len(bulk_load_action_histories(db_session, actions_data))
    assert count == 3
    # Check that the action histories are in the database
    remarks = [a.action_taken_remark for a in db_session.query(ActionHistory).all()]
    assert "Test action" in remarks
    assert "Bulk second action" in remarks
    assert "Bulk third action" in remarks


def test_unique_constraint_district_id(db_session, sample_district_data):
    """Test that duplicate district dist_id raises IntegrityError."""
    create_or_update_district(db_session, sample_district_data)
    duplicate = DistrictSchema(distName="Another District", distId=1)
    with pytest.raises(IntegrityError):
        # Directly add to session to test constraint
        db_session.add(District(dist_name="New name", dist_id=duplicate.dist_id))
        db_session.commit()


def test_unique_constraint_complaint_ticket_no(db_session, sample_complaint_data):
    """Test that duplicate complaint ticket_no raises IntegrityError."""
    create_or_update_complaint(db_session, sample_complaint_data)
    duplicate = sample_complaint_data.model_copy(
        deep=True, update={"petitioner_name": "Jane Doe"}
    ).model_dump(by_alias=False)
    with pytest.raises(IntegrityError):
        db_session.add(Complaint(**duplicate))
        db_session.commit()


def test_unique_constraint_action_history(db_session, sample_action_history_data):
    """Test that duplicate action history (composite unique) raises IntegrityError."""
    create_action_history(db_session, sample_action_history_data)
    duplicate = sample_action_history_data.model_copy(deep=True)
    with pytest.raises(IntegrityError):
        db_session.add(
            ActionHistory(
                ticket_no=duplicate.ticket_no,
                action_taken_by=duplicate.action_taken_by,
                action_status=duplicate.action_status,
                action_taken_remark=duplicate.action_taken_remark,
                complaint_status_with_authority=duplicate.complaint_status_with_authority,
                action_taken_date=duplicate.action_taken_date,
            )
        )
        db_session.commit()


# API Request Tracking tests
def test_record_api_request_success_new(db_session):
    """Test recording a successful API request for the first time."""
    from app.db.crud import record_complaint_api_request_success

    tracking = record_complaint_api_request_success(
        db_session, year=2026, dist_id=1, status=1, office=1, record_count=50
    )

    assert tracking.year == 2026
    assert tracking.dist_id == 1
    assert tracking.status == 1
    assert tracking.office == 1
    assert tracking.records_count == 50
    assert tracking.failure_count == 0
    assert tracking.last_successful_fetch is not None


def test_record_api_request_success_update(db_session):
    """Test updating an existing successful API request."""
    import time

    from app.db.crud import record_complaint_api_request_success

    # First record
    tracking1 = record_complaint_api_request_success(
        db_session, year=2026, dist_id=1, status=1, office=1, record_count=50
    )

    # Small delay to ensure different timestamps
    time.sleep(0.001)

    # Update with new record count
    tracking2 = record_complaint_api_request_success(
        db_session, year=2026, dist_id=1, status=1, office=1, record_count=75
    )

    assert tracking1.id == tracking2.id  # Same record
    assert tracking2.records_count == 75
    assert tracking2.failure_count == 0
    assert tracking2.last_successful_fetch >= tracking1.last_successful_fetch


def test_record_api_request_success_resets_failure_count(db_session):
    """Test that successful API request resets failure count."""
    from app.db.crud import (mark_complaints_api_request_failed,
                             record_complaint_api_request_success)

    # First mark as failed
    mark_complaints_api_request_failed(
        db_session, year=2026, dist_id=1, status=1, office=1
    )
    mark_complaints_api_request_failed(
        db_session, year=2026, dist_id=1, status=1, office=1
    )

    # Check failure count
    tracking = (
        db_session.query(APIRequestTracking)
        .filter(
            APIRequestTracking.year == 2026,
            APIRequestTracking.dist_id == 1,
            APIRequestTracking.status == 1,
            APIRequestTracking.office == 1,
        )
        .first()
    )
    assert tracking.failure_count == 2

    # Now record success
    success_tracking = record_complaint_api_request_success(
        db_session, year=2026, dist_id=1, status=1, office=1, record_count=50
    )

    assert success_tracking.failure_count == 0
    assert success_tracking.records_count == 50


def test_filter_api_request_not_processed(db_session):
    """Test filtering API request that hasn't been processed recently."""
    from app.db.crud import filter_complaints_api_request

    # Should return False for new request
    result = filter_complaints_api_request(
        db_session, year=2026, dist_id=1, status=1, office=1
    )
    assert result is False


def test_filter_api_request_recently_processed(db_session):
    """Test filtering API request that was recently processed successfully."""
    from app.db.crud import (filter_complaints_api_request,
                             record_complaint_api_request_success)

    # Record a successful request
    record_complaint_api_request_success(
        db_session, year=2026, dist_id=1, status=1, office=1, record_count=50
    )

    # Should return True for recently processed request
    result = filter_complaints_api_request(
        db_session, year=2026, dist_id=1, status=1, office=1, days_threshold=7
    )
    assert result is True


def test_filter_api_request_old_processed(db_session):
    """Test filtering API request that was processed but is old."""
    from datetime import datetime, timedelta

    import pytz

    from app.db.crud import (filter_complaints_api_request,
                             record_complaint_api_request_success)

    # Record a successful request with old timestamp
    tracking = APIRequestTracking(
        year=2026,
        dist_id=1,
        status=1,
        office=1,
        records_count=50,
        failure_count=0,
        last_successful_fetch=datetime.now(pytz.timezone("Asia/Kolkata"))
        - timedelta(days=10),
    )
    db_session.add(tracking)
    db_session.commit()

    # Should return False for old request (within 7 day threshold)
    result = filter_complaints_api_request(
        db_session, year=2026, dist_id=1, status=1, office=1, days_threshold=7
    )
    assert result is False

    # Should return True for old request (within 15 day threshold)
    result = filter_complaints_api_request(
        db_session, year=2026, dist_id=1, status=1, office=1, days_threshold=15
    )
    assert result is True


def test_filter_api_request_too_many_failures(db_session):
    """Test filtering API request that has failed too many times."""
    from app.db.crud import (filter_complaints_api_request,
                             mark_complaints_api_request_failed)

    # Mark as failed multiple times
    for _ in range(4):  # More than failure_threshold of 3
        mark_complaints_api_request_failed(
            db_session, year=2026, dist_id=1, status=1, office=1
        )

    # Get record from db
    tracking = (
        db_session.query(APIRequestTracking)
        .filter(
            APIRequestTracking.year == 2026,
            APIRequestTracking.dist_id == 1,
            APIRequestTracking.status == 1,
            APIRequestTracking.office == 1,
        )
        .first()
    )
    assert tracking.failure_count == 4

    # Should return True for request with too many failures
    result = filter_complaints_api_request(
        db_session, year=2026, dist_id=1, status=1, office=1, failure_threshold=3
    )
    assert result is True


def test_filter_api_request_few_failures(db_session):
    """Test filtering API request that has few failures."""
    from app.db.crud import (filter_complaints_api_request,
                             mark_complaints_api_request_failed)

    # Mark as failed few times
    for _ in range(2):  # Less than failure_threshold of 3
        mark_complaints_api_request_failed(
            db_session, year=2026, dist_id=1, status=1, office=1
        )

    # Should return False for request with few failures and no recent success
    result = filter_complaints_api_request(
        db_session, year=2026, dist_id=1, status=1, office=1, failure_threshold=3
    )
    assert result is False


def test_mark_api_request_failed_new(db_session):
    """Test marking a new API request as failed."""
    from app.db.crud import mark_complaints_api_request_failed

    tracking = mark_complaints_api_request_failed(
        db_session, year=2026, dist_id=1, status=1, office=1
    )

    assert tracking.year == 2026
    assert tracking.dist_id == 1
    assert tracking.status == 1
    assert tracking.office == 1
    assert tracking.failure_count == 1
    assert tracking.records_count is None


def test_mark_api_request_failed_increment(db_session):
    """Test incrementing failure count for existing API request."""
    from app.db.crud import mark_complaints_api_request_failed

    # First failure
    tracking1 = mark_complaints_api_request_failed(
        db_session, year=2026, dist_id=1, status=1, office=1
    )
    assert tracking1.failure_count == 1

    # Second failure
    tracking2 = mark_complaints_api_request_failed(
        db_session, year=2026, dist_id=1, status=1, office=1
    )
    assert tracking2.failure_count == 2
    assert tracking1.id == tracking2.id  # Same record


def test_mark_api_request_failed_preserves_success_data(db_session):
    """Test that marking as failed preserves existing success data."""
    from app.db.crud import (mark_complaints_api_request_failed,
                             record_complaint_api_request_success)

    # First record success
    success_tracking = record_complaint_api_request_success(
        db_session, year=2026, dist_id=1, status=1, office=1, record_count=50
    )

    # Then mark as failed
    failed_tracking = mark_complaints_api_request_failed(
        db_session, year=2026, dist_id=1, status=1, office=1
    )

    assert failed_tracking.records_count == 50  # Preserved
    assert failed_tracking.failure_count == 1  # Incremented
    assert (
        failed_tracking.last_successful_fetch == success_tracking.last_successful_fetch
    )  # Preserved


def test_api_request_tracking_unique_constraint(db_session):
    """Test that duplicate API request tracking raises IntegrityError."""
    from app.db.crud import record_complaint_api_request_success

    # First record
    record_complaint_api_request_success(
        db_session, year=2026, dist_id=1, status=1, office=1, record_count=50
    )

    # Try to create duplicate
    with pytest.raises(IntegrityError):
        duplicate = APIRequestTracking(
            year=2026, dist_id=1, status=1, office=1, records_count=75
        )
        db_session.add(duplicate)
        db_session.commit()


def test_api_request_tracking_different_combinations(db_session):
    """Test that different API request combinations are tracked separately."""
    from app.db.crud import (filter_complaints_api_request,
                             record_complaint_api_request_success)

    # Record different combinations
    record_complaint_api_request_success(
        db_session, year=2024, dist_id=1, status=1, office=1, record_count=50
    )
    record_complaint_api_request_success(
        db_session, year=2024, dist_id=2, status=1, office=1, record_count=30
    )
    record_complaint_api_request_success(
        db_session, year=2024, dist_id=1, status=2, office=1, record_count=20
    )

    # Check that they are tracked separately
    assert (
        filter_complaints_api_request(
            db_session, year=2024, dist_id=1, status=1, office=1
        )
        is True
    )
    assert (
        filter_complaints_api_request(
            db_session, year=2024, dist_id=2, status=1, office=1
        )
        is True
    )
    assert (
        filter_complaints_api_request(
            db_session, year=2024, dist_id=1, status=2, office=1
        )
        is True
    )
    assert (
        filter_complaints_api_request(
            db_session, year=2024, dist_id=3, status=1, office=1
        )
        is False
    )


def test_api_request_tracking_error_handling(db_session):
    """Test error handling in API request tracking."""
    from sqlalchemy.exc import OperationalError

    from app.db.crud import (filter_complaints_api_request,
                             mark_complaints_api_request_failed,
                             record_complaint_api_request_success)

    # Test with invalid database session (closed session)
    db_session.bind.dispose()

    # These should raise exceptions with closed session
    with pytest.raises(OperationalError):
        record_complaint_api_request_success(
            db_session, year=2024, dist_id=1, status=1, office=1, record_count=50
        )

    # filter_api_request should return False on error
    result = filter_complaints_api_request(
        db_session, year=2024, dist_id=1, status=1, office=1
    )
    assert result is False

    with pytest.raises(OperationalError):
        mark_complaints_api_request_failed(
            db_session, year=2024, dist_id=1, status=1, office=1
        )


# Action History API Request Tracking Tests
def test_record_action_history_api_request_success_new(db_session):
    """Test recording successful action history API request for new ticket."""
    from app.db.crud import record_action_history_api_request_success

    # Test recording success for a new ticket
    tracking = record_action_history_api_request_success(db_session, "T123", 5)

    assert tracking.ticket_no == "T123"
    assert tracking.records_count == 5
    assert tracking.failure_count == 0
    assert tracking.last_successful_fetch is not None


def test_record_action_history_api_request_success_update(db_session):
    """Test updating existing action history API request tracking."""
    import time

    from app.db.crud import record_action_history_api_request_success

    # First record a success
    tracking = record_action_history_api_request_success(db_session, "T123", 3)
    first_time = tracking.last_successful_fetch

    # Add a small delay to ensure timestamps are different
    time.sleep(0.01)

    # Then update it with new data
    record_action_history_api_request_success(db_session, "T123", 7)

    assert tracking.ticket_no == "T123"
    assert tracking.records_count == 7  # Updated
    assert tracking.failure_count == 0  # Reset
    assert tracking.last_successful_fetch > first_time


def test_record_action_history_api_request_success_resets_failure_count(db_session):
    """Test that successful API request resets failure count."""
    from app.db.crud import (mark_action_history_api_request_failed,
                             record_action_history_api_request_success)

    # First mark as failed multiple times
    mark_action_history_api_request_failed(db_session, "T123")
    mark_action_history_api_request_failed(db_session, "T123")

    # Then record success
    tracking = record_action_history_api_request_success(db_session, "T123", 5)

    assert tracking.failure_count == 0  # Should be reset


def test_mark_action_history_api_request_failed_new(db_session):
    """Test marking action history API request as failed for new ticket."""
    from app.db.crud import mark_action_history_api_request_failed

    # Test marking failure for a new ticket
    tracking = mark_action_history_api_request_failed(db_session, "T123")

    assert tracking.ticket_no == "T123"
    assert tracking.failure_count == 1
    assert tracking.last_successful_fetch is None
    assert tracking.records_count is None


def test_mark_action_history_api_request_failed_increment(db_session):
    """Test incrementing failure count for existing action history tracking."""
    from app.db.crud import mark_action_history_api_request_failed

    # First failure
    tracking1 = mark_action_history_api_request_failed(db_session, "T123")
    assert tracking1.failure_count == 1

    # Second failure
    tracking2 = mark_action_history_api_request_failed(db_session, "T123")
    assert tracking2.failure_count == 2

    # Third failure
    tracking3 = mark_action_history_api_request_failed(db_session, "T123")
    assert tracking3.failure_count == 3


def test_mark_action_history_api_request_failed_preserves_success_data(db_session):
    """Test that marking failure preserves existing success data."""
    from app.db.crud import (mark_action_history_api_request_failed,
                             record_action_history_api_request_success)

    # First record success
    success_tracking = record_action_history_api_request_success(db_session, "T123", 5)
    original_success_time = success_tracking.last_successful_fetch
    original_records_count = success_tracking.records_count

    # Then mark as failed
    failed_tracking = mark_action_history_api_request_failed(db_session, "T123")

    # Success data should be preserved
    assert failed_tracking.last_successful_fetch == original_success_time
    assert failed_tracking.records_count == original_records_count
    assert failed_tracking.failure_count == 1


def test_get_complaints_needing_action_history_empty(db_session):
    """Test getting complaints needing action history when none exist."""
    from app.db.crud import get_tickets_needing_action_history

    # Should return empty list when no complaints exist
    result = get_tickets_needing_action_history(db_session)
    assert result == []


def test_get_complaints_needing_action_history_recent_success(
    db_session, sample_complaint_data
):
    """Test that recently successful requests are not returned."""
    from app.db.crud import (create_or_update_complaint,
                             get_tickets_needing_action_history,
                             record_action_history_api_request_success)

    # Create a complaint first
    create_or_update_complaint(db_session, sample_complaint_data)

    # Record a recent success (within threshold)
    record_action_history_api_request_success(db_session, "T123", 5)

    # Should not return this ticket as it was recently successful
    result = get_tickets_needing_action_history(db_session, days_threshold=7)
    assert len(result) == 0


def test_get_complaints_needing_action_history_old_success(
    db_session, sample_complaint_data
):
    """Test that old successful requests are returned."""
    from datetime import datetime, timedelta

    import pytz

    from app.db.crud import (create_or_update_complaint,
                             get_tickets_needing_action_history)

    # Create a complaint first
    create_or_update_complaint(db_session, sample_complaint_data)

    # Create a tracking record with old success time
    time_zone = pytz.timezone("Asia/Kolkata")
    old_time = datetime.now(time_zone) - timedelta(days=10)  # 10 days ago

    # Manually create tracking record with old time
    from app.db.models import ActionHistoryAPIRequestTracking

    tracking = ActionHistoryAPIRequestTracking(
        ticket_no="T123",
        last_successful_fetch=old_time,
        records_count=5,
        failure_count=0,
    )
    db_session.add(tracking)
    db_session.commit()

    # Should return this ticket as it was successful but old
    result = get_tickets_needing_action_history(db_session, days_threshold=7)
    assert len(result) == 1
    assert "T123" in result


def test_get_complaints_needing_action_history_too_many_failures(
    db_session, sample_complaint_data
):
    """Test that tickets with too many failures are not returned."""
    from app.db.crud import (create_or_update_complaint,
                             get_tickets_needing_action_history,
                             mark_action_history_api_request_failed)

    # Create a complaint first
    create_or_update_complaint(db_session, sample_complaint_data)

    # Mark multiple failures
    for _ in range(5):  # More than threshold
        mark_action_history_api_request_failed(db_session, "T123")

    # Should not return this ticket as it has too many failures
    result = get_tickets_needing_action_history(db_session, failure_threshold=3)
    assert len(result) == 0


def test_get_complaints_needing_action_history_few_failures(
    db_session, sample_complaint_data
):
    """Test that tickets with few failures are returned."""
    from app.db.crud import (create_or_update_complaint,
                             get_tickets_needing_action_history,
                             mark_action_history_api_request_failed)

    # Create a complaint first
    create_or_update_complaint(db_session, sample_complaint_data)

    # Mark only 2 failures (below threshold)
    mark_action_history_api_request_failed(db_session, "T123")
    mark_action_history_api_request_failed(db_session, "T123")

    # Should return this ticket as it has few failures
    result = get_tickets_needing_action_history(db_session, failure_threshold=3)
    assert len(result) == 1
    assert "T123" in result


def test_get_complaints_needing_action_history_mixed_scenarios(
    db_session, sample_complaint_data
):
    """Test multiple scenarios in the same database."""
    from datetime import datetime, timedelta

    import pytz

    from app.db.crud import (create_or_update_complaint,
                             get_tickets_needing_action_history,
                             mark_action_history_api_request_failed,
                             record_action_history_api_request_success)

    # Create multiple complaints
    create_or_update_complaint(db_session, sample_complaint_data)

    # Create additional complaints
    complaint2 = sample_complaint_data.model_copy(
        update={"ticket_no": "T456"}, deep=True
    )
    complaint3 = sample_complaint_data.model_copy(
        update={"ticket_no": "T789"}, deep=True
    )
    complaint4 = sample_complaint_data.model_copy(
        update={"ticket_no": "T101"}, deep=True
    )

    complaint2 = create_or_update_complaint(db_session, complaint2)
    create_or_update_complaint(db_session, complaint3)
    create_or_update_complaint(db_session, complaint4)

    time_zone = pytz.timezone("Asia/Kolkata")
    old_time = datetime.now(time_zone) - timedelta(days=10)

    # Scenario 1: Recent success (should not be returned)
    record_action_history_api_request_success(db_session, "T123", 5)

    # Scenario 2: Old success (should be returned)
    from app.db.models import ActionHistoryAPIRequestTracking

    old_tracking = ActionHistoryAPIRequestTracking(
        ticket_no="T456",
        last_successful_fetch=old_time,
        records_count=3,
        failure_count=0,
    )
    db_session.add(old_tracking)

    # Scenario 3: Too many failures (should not be returned)
    for _ in range(5):
        mark_action_history_api_request_failed(db_session, "T789")

    # Scenario 4: Few failures (should be returned)
    mark_action_history_api_request_failed(db_session, "T101")
    mark_action_history_api_request_failed(db_session, "T101")

    db_session.commit()

    # Should return only T456 and T101
    result = get_tickets_needing_action_history(
        db_session, days_threshold=7, failure_threshold=3
    )
    assert len(result) == 2
    assert "T456" in result
    assert "T101" in result
    assert "T123" not in result  # Recent success
    assert "T789" not in result  # Too many failures


def test_action_history_tracking_error_handling(db_session):
    """Test error handling in action history tracking functions."""
    from app.db.crud import (mark_action_history_api_request_failed,
                             record_action_history_api_request_success)

    # Test with invalid data - these should handle None values gracefully
    # The functions don't raise exceptions for None values, they handle them
    tracking1 = record_action_history_api_request_success(db_session, None, None)
    assert tracking1 is not None

    tracking2 = mark_action_history_api_request_failed(db_session, None)
    assert tracking2 is not None


def test_action_history_tracking_database_rollback(db_session):
    """Test that database rollback works correctly on errors."""
    from app.db.crud import record_action_history_api_request_success

    # Create a tracking record
    tracking1 = record_action_history_api_request_success(db_session, "T123", 5)
    original_id = tracking1.id
    original_records_count = tracking1.records_count

    # Try to create another with same ticket_no (should update existing record)
    # This should update the existing record due to unique constraint
    tracking2 = record_action_history_api_request_success(db_session, "T123", 3)

    # Verify the record was updated, not created new
    assert tracking2.id == original_id
    assert tracking2.records_count == 3  # Should be updated
    assert tracking2.records_count != original_records_count  # Should be different


# Document-related CRUD tests
def test_get_complaints_without_documents_empty(db_session):
    """Test getting complaints without documents when none exist."""
    from app.db.crud import get_complaints_without_documents

    # Should return empty list when no complaints exist
    result = get_complaints_without_documents(db_session)
    assert result == []


def test_get_complaints_without_documents_no_document_url(
    db_session, sample_complaint_data
):
    """Test that complaints without document_url are not returned."""
    from app.db.crud import (create_or_update_complaint,
                             get_complaints_without_documents)

    # Create a complaint without document_url
    complaint_data = sample_complaint_data.model_copy(update={"document_url": ""})
    create_or_update_complaint(db_session, complaint_data)

    # Should not return complaints without document_url
    result = get_complaints_without_documents(db_session)
    assert len(result) == 0


def test_get_complaints_without_documents_already_downloaded(
    db_session, sample_complaint_data
):
    """Test that complaints with already downloaded documents are not returned."""
    from app.db.crud import (create_or_update_complaint,
                             get_complaints_without_documents,
                             update_document_status)

    # Create a complaint with document_url
    create_or_update_complaint(db_session, sample_complaint_data)

    # Mark document as downloaded
    update_document_status(db_session, "T123", "/path/to/document.pdf", True)

    # Should not return complaints with downloaded documents
    result = get_complaints_without_documents(db_session)
    assert len(result) == 0


def test_get_complaints_without_documents_needs_download(
    db_session, sample_complaint_data
):
    """Test that complaints with document_url but not downloaded are returned."""
    from app.db.crud import (create_or_update_complaint,
                             get_complaints_without_documents)

    # Create a complaint with document_url
    create_or_update_complaint(db_session, sample_complaint_data)

    # Should return complaints with document_url but not downloaded
    result = get_complaints_without_documents(db_session)
    assert len(result) == 1
    assert result[0].ticket_no == "T123"
    assert result[0].document_url == "example.pdf"
    assert result[0].document_downloaded == False


def test_get_complaints_without_documents_mixed_scenarios(
    db_session, sample_complaint_data
):
    """Test multiple scenarios in the same database."""
    from app.db.crud import (create_or_update_complaint,
                             get_complaints_without_documents,
                             update_document_status)

    # Create multiple complaints with different scenarios
    create_or_update_complaint(
        db_session, sample_complaint_data
    )  # Has document_url, not downloaded

    # Complaint without document_url
    complaint2 = sample_complaint_data.model_copy(
        update={"ticket_no": "T456", "document_url": ""}
    )
    create_or_update_complaint(db_session, complaint2)

    # Complaint with downloaded document
    complaint3 = sample_complaint_data.model_copy(update={"ticket_no": "T789"})
    create_or_update_complaint(db_session, complaint3)
    update_document_status(db_session, "T789", "/path/to/document.pdf", True)

    # Complaint with document_url but not downloaded
    complaint4 = sample_complaint_data.model_copy(update={"ticket_no": "T101"})
    create_or_update_complaint(db_session, complaint4)

    # Should return only T123 and T101 (have document_url but not downloaded)
    result = get_complaints_without_documents(db_session)
    assert len(result) == 2
    ticket_nos = [complaint.ticket_no for complaint in result]
    assert "T123" in ticket_nos
    assert "T101" in ticket_nos
    assert "T456" not in ticket_nos  # No document_url
    assert "T789" not in ticket_nos  # Already downloaded


def test_get_complaints_without_documents_download_error(
    db_session, sample_complaint_data
):
    """Test that complaints with download errors are still returned."""
    from app.db.crud import (create_or_update_complaint,
                             get_complaints_without_documents,
                             update_document_status)

    # Create a complaint with document_url
    create_or_update_complaint(db_session, sample_complaint_data)

    # Mark document as failed download
    update_document_status(db_session, "T123", None, False, "Network error")

    # Should still return complaints with download errors (not downloaded)
    result = get_complaints_without_documents(
        db_session, get_docs_where_errors_occurred=True
    )
    assert len(result) == 1
    assert result[0].ticket_no == "T123"
    assert result[0].document_downloaded == False
    assert result[0].document_download_error == "Network error"

    result2 = get_complaints_without_documents(
        db_session, get_docs_where_errors_occurred=False
    )
    assert len(result2) == 0


def test_get_complaints_without_documents_partial_download(
    db_session, sample_complaint_data
):
    """Test that complaints with partial download info are handled correctly."""
    from app.db.crud import (create_or_update_complaint,
                             get_complaints_without_documents,
                             update_document_status)

    # Create a complaint with document_url
    create_or_update_complaint(db_session, sample_complaint_data)

    # Mark document as downloaded with local path
    update_document_status(db_session, "T123", "/local/path/document.pdf", True)

    # Should not return complaints with downloaded documents
    result = get_complaints_without_documents(db_session)
    assert len(result) == 0


def test_get_complaints_without_documents_multiple_complaints(
    db_session, sample_complaint_data
):
    """Test with multiple complaints needing document download."""
    from app.db.crud import (create_or_update_complaint,
                             get_complaints_without_documents)

    # Create multiple complaints with document_urls
    complaints = []
    for i in range(5):
        complaint = sample_complaint_data.model_copy(update={"ticket_no": f"T{i+100}"})
        create_or_update_complaint(db_session, complaint)
        complaints.append(complaint)

    # Should return all complaints with document_urls
    result = get_complaints_without_documents(db_session)
    assert len(result) == 5

    # Verify all returned complaints have document_urls and are not downloaded
    for complaint in result:
        assert complaint.document_url is not None
        assert complaint.document_downloaded == False


def test_get_complaints_without_documents_edge_case_none_document_url(
    db_session, sample_complaint_data
):
    """Test edge case where document_url is explicitly None."""
    from app.db.crud import (create_or_update_complaint,
                             get_complaints_without_documents)

    # Create a complaint with explicit None document_url
    complaint_data = sample_complaint_data.model_copy(update={"document_url": None})
    create_or_update_complaint(db_session, complaint_data)

    # Should not return complaints with None document_url
    result = get_complaints_without_documents(db_session)
    assert len(result) == 0


def test_get_complaints_without_documents_edge_case_empty_document_url(
    db_session, sample_complaint_data
):
    """Test edge case where document_url is empty string."""
    from app.db.crud import (create_or_update_complaint,
                             get_complaints_without_documents)

    # Create a complaint with empty document_url
    complaint_data = sample_complaint_data.model_copy(update={"document_url": ""})
    create_or_update_complaint(db_session, complaint_data)

    # The function uses document_url.isnot(None), so empty strings ARE included
    # This is the actual behavior of the function
    result = get_complaints_without_documents(db_session)
    assert len(result) == 0


# Document Status Update Tests
def test_update_document_status_success(db_session, sample_complaint_data):
    """Test successful document status update."""
    from app.db.crud import create_or_update_complaint, update_document_status

    # Create a complaint first
    create_or_update_complaint(db_session, sample_complaint_data)

    # Update document status
    result = update_document_status(
        db_session,
        ticket_no="T123",
        local_path="/path/to/document.pdf",
        success=True,
        error=None,
    )

    assert result is not None
    assert result.ticket_no == "T123"
    assert result.local_document_path == "/path/to/document.pdf"
    assert result.document_downloaded is True
    assert result.document_download_error is None
    assert result.document_download_date is not None


def test_update_document_status_failure(db_session, sample_complaint_data):
    """Test document status update for failed download."""
    from app.db.crud import create_or_update_complaint, update_document_status

    # Create a complaint first
    create_or_update_complaint(db_session, sample_complaint_data)

    # Update document status for failed download
    result = update_document_status(
        db_session,
        ticket_no="T123",
        local_path=None,
        success=False,
        error="Network timeout",
    )

    assert result is not None
    assert result.ticket_no == "T123"
    assert result.local_document_path is None
    assert result.document_downloaded is False
    assert result.document_download_error == "Network timeout"
    assert result.document_download_date is not None


def test_update_document_status_nonexistent_ticket(db_session):
    """Test document status update for non-existent ticket."""
    from app.db.crud import update_document_status

    # Try to update status for non-existent ticket
    result = update_document_status(
        db_session,
        ticket_no="NONEXISTENT",
        local_path="/path/to/document.pdf",
        success=True,
        error=None,
    )

    assert result is None


def test_update_document_status_updates_existing_fields(
    db_session, sample_complaint_data
):
    """Test that update_document_status properly updates existing fields."""
    from app.db.crud import create_or_update_complaint, update_document_status

    # Create a complaint first
    create_or_update_complaint(db_session, sample_complaint_data)

    # Initial update
    result1 = update_document_status(
        db_session,
        ticket_no="T123",
        local_path="/path/to/document1.pdf",
        success=True,
        error=None,
    )

    # Second update - should overwrite previous values
    result2 = update_document_status(
        db_session,
        ticket_no="T123",
        local_path="/path/to/document2.pdf",
        success=False,
        error="New error",
    )

    assert result2 is not None
    assert result2.ticket_no == "T123"
    assert result2.local_document_path == "/path/to/document2.pdf"
    assert result2.document_downloaded is False
    assert result2.document_download_error == "New error"
    assert result2.document_download_date is not None


def test_update_document_status_preserves_other_fields(
    db_session, sample_complaint_data
):
    """Test that update_document_status doesn't affect other complaint fields."""
    from app.db.crud import create_or_update_complaint, update_document_status

    # Create a complaint first
    create_or_update_complaint(db_session, sample_complaint_data)

    # Get original complaint
    original_complaint = get_complaint_by_ticket(db_session, "T123")
    original_petitioner_name = original_complaint.petitioner_name
    original_office = original_complaint.office

    # Update document status
    result = update_document_status(
        db_session,
        ticket_no="T123",
        local_path="/path/to/document.pdf",
        success=True,
        error=None,
    )

    # Verify other fields are preserved
    assert result.petitioner_name == original_petitioner_name
    assert result.office == original_office
    assert result.grievance == original_complaint.grievance
    assert result.district == original_complaint.district


def test_update_document_status_with_empty_strings(db_session, sample_complaint_data):
    """Test document status update with empty string values."""
    from app.db.crud import create_or_update_complaint, update_document_status

    # Create a complaint first
    create_or_update_complaint(db_session, sample_complaint_data)

    # Update with empty strings
    result = update_document_status(
        db_session, ticket_no="T123", local_path="", success=False, error=""
    )

    assert result is not None
    assert result.local_document_path == ""
    assert result.document_downloaded is False
    assert result.document_download_error == ""


def test_update_document_status_multiple_complaints(db_session, sample_complaint_data):
    """Test updating document status for multiple complaints."""
    from app.db.crud import create_or_update_complaint, update_document_status

    # Create multiple complaints
    complaint1 = sample_complaint_data.model_copy(update={"ticket_no": "T123"})
    complaint2 = sample_complaint_data.model_copy(update={"ticket_no": "T456"})
    complaint3 = sample_complaint_data.model_copy(update={"ticket_no": "T789"})

    create_or_update_complaint(db_session, complaint1)
    create_or_update_complaint(db_session, complaint2)
    create_or_update_complaint(db_session, complaint3)

    # Update each complaint with different statuses
    result1 = update_document_status(
        db_session, "T123", "/path/to/doc1.pdf", True, None
    )
    result2 = update_document_status(db_session, "T456", None, False, "Download failed")
    result3 = update_document_status(
        db_session, "T789", "/path/to/doc3.pdf", True, None
    )

    # Verify all updates worked
    assert result1 is not None and result1.document_downloaded is True
    assert result2 is not None and result2.document_downloaded is False
    assert result3 is not None and result3.document_downloaded is True


def test_update_document_status_database_commit(db_session, sample_complaint_data):
    """Test that update_document_status properly commits to database."""
    from app.db.crud import (create_or_update_complaint,
                             get_complaint_by_ticket, update_document_status)

    # Create a complaint first
    create_or_update_complaint(db_session, sample_complaint_data)

    # Update document status
    result = update_document_status(
        db_session,
        ticket_no="T123",
        local_path="/path/to/document.pdf",
        success=True,
        error=None,
    )

    # Verify the update was committed by querying the database again
    updated_complaint = get_complaint_by_ticket(db_session, "T123")
    assert updated_complaint is not None
    assert updated_complaint.local_document_path == "/path/to/document.pdf"
    assert updated_complaint.document_downloaded is True
    assert updated_complaint.document_download_error is None
    assert updated_complaint.document_download_date is not None


# TODO: Add this test back in when we have a way to test the timezone since SQLite Datetime does not store timezone information
# def test_update_document_status_timezone_handling(db_session, sample_complaint_data):
#     """Test that update_document_status uses correct timezone."""
#     from app.db.crud import create_or_update_complaint, update_document_status
#     import pytz

#     # Create a complaint first
#     create_or_update_complaint(db_session, sample_complaint_data)

#     # Update document status
#     result = update_document_status(
#         db_session,
#         ticket_no="T123",
#         local_path="/path/to/document.pdf",
#         success=True,
#         error=None
#     )

#     # Verify timezone is Asia/Kolkata
#     assert result.document_download_date is not None
#     assert result.document_download_date.tzinfo == pytz.timezone("Asia/Kolkata")


def test_update_document_status_deprecation_warning(db_session, sample_complaint_data):
    """Test that update_document_status raises deprecation warning."""
    import warnings

    from app.db.crud import create_or_update_complaint, update_document_status

    # Create a complaint first
    create_or_update_complaint(db_session, sample_complaint_data)

    # Capture warnings
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        result = update_document_status(
            db_session,
            ticket_no="T123",
            local_path="/path/to/document.pdf",
            success=True,
            error=None,
        )

        # Verify deprecation warning was raised
        assert len(w) == 1
        assert issubclass(w[0].category, DeprecationWarning)
        assert "deprecated" in str(w[0].message)


def test_update_document_status_error_handling(db_session):
    """Test error handling in update_document_status."""
    from app.db.crud import update_document_status

    # Test with invalid database session
    db_session.bind.dispose()

    # Should handle gracefully or raise appropriate exception
    try:
        result = update_document_status(
            db_session,
            ticket_no="T123",
            local_path="/path/to/document.pdf",
            success=True,
            error=None,
        )
        # If it doesn't raise an exception, result should be None
        assert result is None
    except Exception as e:
        # If it raises an exception, it should be a database-related error
        assert (
            "database" in str(e).lower()
            or "connection" in str(e).lower()
            or "operationalerror" in str(e).lower()
        )


def test_update_document_status_edge_cases(db_session, sample_complaint_data):
    """Test edge cases for update_document_status."""
    from app.db.crud import create_or_update_complaint, update_document_status

    # Create a complaint first
    create_or_update_complaint(db_session, sample_complaint_data)

    # Test with very long path
    long_path = "/" + "a" * 1000 + "/document.pdf"
    result1 = update_document_status(db_session, "T123", long_path, True, None)
    assert result1.local_document_path == long_path

    # Test with special characters in error message
    special_error = "Error: File 'test~pdf' not found! @#$%^&*()"
    result2 = update_document_status(
        db_session, "T123", "/path/to/doc.pdf", False, special_error
    )
    assert result2.document_download_error == special_error

    # Test with None values
    result3 = update_document_status(db_session, "T123", None, False, None)
    assert result3.local_document_path is None
    assert result3.document_download_error is None


def test_update_document_status_integration_with_get_complaints_without_documents(
    db_session, sample_complaint_data
):
    """Test integration between update_document_status and get_complaints_without_documents."""
    from app.db.crud import (create_or_update_complaint,
                             get_complaints_without_documents,
                             update_document_status)

    # Create a complaint first
    create_or_update_complaint(db_session, sample_complaint_data)

    # Initially, complaint should be in the list
    complaints_before = get_complaints_without_documents(db_session)
    assert len(complaints_before) == 1
    assert complaints_before[0].ticket_no == "T123"

    # Update document status to downloaded
    update_document_status(db_session, "T123", "/path/to/document.pdf", True, None)

    # Now complaint should not be in the list
    complaints_after = get_complaints_without_documents(db_session)
    assert len(complaints_after) == 0

    # Update document status to failed
    update_document_status(db_session, "T123", None, False, "Download failed")

    # Complaint should be back in the list (not downloaded)
    complaints_failed = get_complaints_without_documents(
        db_session, get_docs_where_errors_occurred=True
    )
    assert len(complaints_failed) == 1
    assert complaints_failed[0].ticket_no == "T123"
    assert complaints_failed[0].document_downloaded is False


def test_update_document_status_performance(db_session, sample_complaint_data):
    """Test performance of update_document_status with multiple updates."""
    import time

    from app.db.crud import create_or_update_complaint, update_document_status

    # Create a complaint first
    create_or_update_complaint(db_session, sample_complaint_data)

    # Measure time for multiple updates
    start_time = time.time()

    for i in range(10):
        update_document_status(
            db_session,
            ticket_no="T123",
            local_path=f"/path/to/document_{i}.pdf",
            success=(i % 2 == 0),
            error=f"Error {i}" if i % 2 == 1 else None,
        )

    end_time = time.time()
    execution_time = end_time - start_time

    # Verify all updates worked
    final_complaint = get_complaint_by_ticket(db_session, "T123")
    assert final_complaint is not None
    assert final_complaint.local_document_path == "/path/to/document_9.pdf"
    assert final_complaint.document_downloaded is False
    assert final_complaint.document_download_error == "Error 9"

    # Performance should be reasonable (less than 1 second for 10 updates)
    assert execution_time < 1.0
