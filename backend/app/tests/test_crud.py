import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.models import Base, District, Complaint, ActionHistory, APIRequestTracking
from app.db.crud import (
    get_district_by_id,
    get_district_by_name,
    create_or_update_district,
    get_all_districts,
    get_complaint_by_ticket,
    create_or_update_complaint,
    get_complaints_by_district,
    get_complaints_by_status,
    create_action_history,
    get_action_history_by_ticket,
    batch_create_or_update_districts,
    batch_create_or_update_complaints,
    batch_create_action_history,
    bulk_load_districts,
    bulk_load_complaints,
    bulk_load_action_histories
)
from app.ingestion.schemas import District as DistrictSchema, Complaint as ComplaintSchema, ActionHistory as ActionHistorySchema
from sqlalchemy.exc import IntegrityError

@pytest.fixture(autouse=True)
def setup_test_environment():
    """
    Set up the test environment for CRUD tests.
    This ensures we use the real OFFICE constant for these tests.
    """
    import sys
    from app.ingestion import schemas
    from app.ingestion import OFFICE as REAL_OFFICE
    
    # Store the original OFFICE if it exists
    original_office = getattr(schemas, 'OFFICE', None)
    
    # Set the real OFFICE constant
    sys.modules["app.ingestion.schemas"].OFFICE = REAL_OFFICE
    
    yield
    
    # Restore the original OFFICE if it existed
    if original_office is not None:
        sys.modules["app.ingestion.schemas"].OFFICE = original_office
    elif hasattr(schemas, 'OFFICE'):
        delattr(schemas, 'OFFICE')


# Test database setup
@pytest.fixture(scope="function")
def db_session():
    """Create a fresh database for each test."""
    # Create in-memory SQLite database for testing
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    
    # Create a new session for the test
    TestingSessionLocal = sessionmaker(bind=engine)
    session = TestingSessionLocal()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)

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
        Document = "example.pdf",
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
        benefitted=None
    )

@pytest.fixture
def sample_action_history_data():
    return ActionHistorySchema(
        ticketNumber="T123",
        action_taken_by="Officer X",
        action_taken_date="2024-03-20T10:00:00",
        action_taken_remark="Test action",
        action_status="Completed",
        complaint_status_with_authority="Pending"
    )

# District CRUD tests
def test_create_district(db_session, sample_district_data):
    """Test creating a new district."""
    district = create_or_update_district(db_session, sample_district_data)
    assert district.dist_id == 1
    assert district.dist_name == "Test District"

def test_get_district_by_id(db_session, sample_district_data):
    """Test retrieving a district by ID."""
    # First create a district
    create_or_update_district(db_session, sample_district_data)
    
    # Then retrieve it
    district = get_district_by_id(db_session, 1)
    assert district is not None
    assert district.dist_name == "Test District"

def test_get_district_by_name(db_session, sample_district_data):
    """Test retrieving a district by name."""
    # First create a district
    create_or_update_district(db_session, sample_district_data)
    
    # Then retrieve it
    district = get_district_by_name(db_session, "Test District")
    assert district is not None
    assert district.dist_id == 1

def test_update_district(db_session, sample_district_data):
    """Test updating an existing district."""
    # First create a district
    create_or_update_district(db_session, sample_district_data)
    
    # Update the district
    updated_data = DistrictSchema(distName="Updated District", distId=1)
    updated_district = create_or_update_district(db_session, updated_data)
    
    assert updated_district.dist_name == "Updated District"
    assert updated_district.dist_id == 1

def test_get_all_districts(db_session, sample_district_data):
    """Test retrieving all districts."""
    # Create multiple districts
    district1 = create_or_update_district(db_session, sample_district_data)
    district2 = create_or_update_district(db_session, DistrictSchema(distName="Test District 2", distId=2))
    
    districts = get_all_districts(db_session)
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
    updated_data = sample_complaint_data.model_copy(update={"petitioner_name": "Jane Doe"})
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
        DistrictSchema(distName="District 3", distId=3)
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
        sample_complaint_data.model_copy(deep=True, update={"ticket_no": "T125"})
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
        sample_action_history_data.model_copy(deep=True, update={"action_taken_remark": "Second action"}),
        sample_action_history_data.model_copy(deep=True, update={"action_taken_remark": "Third action"})
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
        DistrictSchema(distName="Bulk District 3", distId=12)
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
        sample_complaint_data.model_copy(deep=True, update={"ticket_no": "T201"})
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
        sample_action_history_data.model_copy(deep=True, update={"action_taken_remark": "Bulk second action"}),
        sample_action_history_data.model_copy(deep=True, update={"action_taken_remark": "Bulk third action"})
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
    duplicate  = sample_complaint_data.model_copy(deep=True, update={"petitioner_name": "Jane Doe"}).model_dump(by_alias=False)
    with pytest.raises(IntegrityError):
        db_session.add(Complaint(
            **duplicate
        ))
        db_session.commit()

def test_unique_constraint_action_history(db_session, sample_action_history_data):
    """Test that duplicate action history (composite unique) raises IntegrityError."""
    create_action_history(db_session, sample_action_history_data)
    duplicate = sample_action_history_data.model_copy(deep=True)
    with pytest.raises(IntegrityError):
        db_session.add(ActionHistory(
            ticket_no=duplicate.ticket_no,
            action_taken_by=duplicate.action_taken_by,
            action_status=duplicate.action_status,
            action_taken_remark=duplicate.action_taken_remark,
            complaint_status_with_authority=duplicate.complaint_status_with_authority,
            action_taken_date=duplicate.action_taken_date
        ))
        db_session.commit()

# API Request Tracking tests
def test_record_api_request_success_new(db_session):
    """Test recording a successful API request for the first time."""
    from app.db.crud import record_api_request_success
    
    tracking = record_api_request_success(db_session, year=2026, dist_id=1, status=1, office=1, record_count=50)
    
    assert tracking.year == 2026
    assert tracking.dist_id == 1
    assert tracking.status == 1
    assert tracking.office == 1
    assert tracking.records_count == 50
    assert tracking.failure_count == 0
    assert tracking.last_successful_fetch is not None

def test_record_api_request_success_update(db_session):
    """Test updating an existing successful API request."""
    from app.db.crud import record_api_request_success
    import time
    
    # First record
    tracking1 = record_api_request_success(db_session, year=2026, dist_id=1, status=1, office=1, record_count=50)
    
    # Small delay to ensure different timestamps
    time.sleep(0.001)
    
    # Update with new record count
    tracking2 = record_api_request_success(db_session, year=2026, dist_id=1, status=1, office=1, record_count=75)
    
    assert tracking1.id == tracking2.id  # Same record
    assert tracking2.records_count == 75
    assert tracking2.failure_count == 0
    assert tracking2.last_successful_fetch >= tracking1.last_successful_fetch

def test_record_api_request_success_resets_failure_count(db_session):
    """Test that successful API request resets failure count."""
    from app.db.crud import record_api_request_success, mark_api_request_failed
    
    # First mark as failed
    mark_api_request_failed(db_session, year=2026, dist_id=1, status=1, office=1)
    mark_api_request_failed(db_session, year=2026, dist_id=1, status=1, office=1)
    
    # Check failure count
    tracking = db_session.query(APIRequestTracking).filter(
        APIRequestTracking.year == 2026,
        APIRequestTracking.dist_id == 1,
        APIRequestTracking.status == 1,
        APIRequestTracking.office == 1
    ).first()
    assert tracking.failure_count == 2
    
    # Now record success
    success_tracking = record_api_request_success(db_session, year=2026, dist_id=1, status=1, office=1, record_count=50)
    
    assert success_tracking.failure_count == 0
    assert success_tracking.records_count == 50

def test_filter_api_request_not_processed(db_session):
    """Test filtering API request that hasn't been processed recently."""
    from app.db.crud import filter_api_request
    
    # Should return False for new request
    result = filter_api_request(db_session, year=2026, dist_id=1, status=1, office=1)
    assert result is False

def test_filter_api_request_recently_processed(db_session):
    """Test filtering API request that was recently processed successfully."""
    from app.db.crud import filter_api_request, record_api_request_success
    
    # Record a successful request
    record_api_request_success(db_session, year=2026, dist_id=1, status=1, office=1, record_count=50)
    
    # Should return True for recently processed request
    result = filter_api_request(db_session, year=2026, dist_id=1, status=1, office=1, days_threshold=7)
    assert result is True

def test_filter_api_request_old_processed(db_session):
    """Test filtering API request that was processed but is old."""
    from app.db.crud import filter_api_request, record_api_request_success
    from datetime import datetime, timedelta
    import pytz
    
    # Record a successful request with old timestamp
    tracking = APIRequestTracking(
        year=2026,
        dist_id=1,
        status=1,
        office=1,
        records_count=50,
        failure_count=0,
        last_successful_fetch=datetime.now(pytz.timezone('Asia/Kolkata')) - timedelta(days=10)
    )
    db_session.add(tracking)
    db_session.commit()
    
    # Should return False for old request (within 7 day threshold)
    result = filter_api_request(db_session, year=2026, dist_id=1, status=1, office=1, days_threshold=7)
    assert result is False
    
    # Should return True for old request (within 15 day threshold)
    result = filter_api_request(db_session, year=2026, dist_id=1, status=1, office=1, days_threshold=15)
    assert result is True

def test_filter_api_request_too_many_failures(db_session):
    """Test filtering API request that has failed too many times."""
    from app.db.crud import filter_api_request, mark_api_request_failed
    
    # Mark as failed multiple times
    for _ in range(4):  # More than failure_threshold of 3
        mark_api_request_failed(db_session, year=2026, dist_id=1, status=1, office=1)

    # Get record from db
    tracking = db_session.query(APIRequestTracking).filter(
        APIRequestTracking.year == 2026,
        APIRequestTracking.dist_id == 1,
        APIRequestTracking.status == 1,
        APIRequestTracking.office == 1
    ).first()
    assert tracking.failure_count == 4
    
    # Should return True for request with too many failures
    result = filter_api_request(db_session, year=2026, dist_id=1, status=1, office=1, failure_threshold=3)
    assert result is True

def test_filter_api_request_few_failures(db_session):
    """Test filtering API request that has few failures."""
    from app.db.crud import filter_api_request, mark_api_request_failed
    
    # Mark as failed few times
    for _ in range(2):  # Less than failure_threshold of 3
        mark_api_request_failed(db_session, year=2026, dist_id=1, status=1, office=1)
    
    # Should return False for request with few failures and no recent success
    result = filter_api_request(db_session, year=2026, dist_id=1, status=1, office=1, failure_threshold=3)
    assert result is False

def test_mark_api_request_failed_new(db_session):
    """Test marking a new API request as failed."""
    from app.db.crud import mark_api_request_failed
    
    tracking = mark_api_request_failed(db_session, year=2026, dist_id=1, status=1, office=1)
    
    assert tracking.year == 2026
    assert tracking.dist_id == 1
    assert tracking.status == 1
    assert tracking.office == 1
    assert tracking.failure_count == 1
    assert tracking.records_count is None

def test_mark_api_request_failed_increment(db_session):
    """Test incrementing failure count for existing API request."""
    from app.db.crud import mark_api_request_failed
    
    # First failure
    tracking1 = mark_api_request_failed(db_session, year=2026, dist_id=1, status=1, office=1)
    assert tracking1.failure_count == 1
    
    # Second failure
    tracking2 = mark_api_request_failed(db_session, year=2026, dist_id=1, status=1, office=1)
    assert tracking2.failure_count == 2
    assert tracking1.id == tracking2.id  # Same record

def test_mark_api_request_failed_preserves_success_data(db_session):
    """Test that marking as failed preserves existing success data."""
    from app.db.crud import mark_api_request_failed, record_api_request_success
    
    # First record success
    success_tracking = record_api_request_success(db_session, year=2026, dist_id=1, status=1, office=1, record_count=50)
    
    # Then mark as failed
    failed_tracking = mark_api_request_failed(db_session, year=2026, dist_id=1, status=1, office=1)
    
    assert failed_tracking.records_count == 50  # Preserved
    assert failed_tracking.failure_count == 1   # Incremented
    assert failed_tracking.last_successful_fetch == success_tracking.last_successful_fetch  # Preserved

def test_api_request_tracking_unique_constraint(db_session):
    """Test that duplicate API request tracking raises IntegrityError."""
    from app.db.crud import record_api_request_success
    
    # First record
    record_api_request_success(db_session, year=2026, dist_id=1, status=1, office=1, record_count=50)
    
    # Try to create duplicate
    with pytest.raises(IntegrityError):
        duplicate = APIRequestTracking(
            year=2026,
            dist_id=1,
            status=1,
            office=1,
            records_count=75
        )
        db_session.add(duplicate)
        db_session.commit()

def test_api_request_tracking_different_combinations(db_session):
    """Test that different API request combinations are tracked separately."""
    from app.db.crud import record_api_request_success, filter_api_request
    
    # Record different combinations
    record_api_request_success(db_session, year=2024, dist_id=1, status=1, office=1, record_count=50)
    record_api_request_success(db_session, year=2024, dist_id=2, status=1, office=1, record_count=30)
    record_api_request_success(db_session, year=2024, dist_id=1, status=2, office=1, record_count=20)
    
    # Check that they are tracked separately
    assert filter_api_request(db_session, year=2024, dist_id=1, status=1, office=1) is True
    assert filter_api_request(db_session, year=2024, dist_id=2, status=1, office=1) is True
    assert filter_api_request(db_session, year=2024, dist_id=1, status=2, office=1) is True
    assert filter_api_request(db_session, year=2024, dist_id=3, status=1, office=1) is False

def test_api_request_tracking_error_handling(db_session):
    """Test error handling in API request tracking functions."""
    from app.db.crud import record_api_request_success, filter_api_request, mark_api_request_failed
    from sqlalchemy.exc import ResourceClosedError
    
    # Test with invalid database session (closed session)
    db_session.close()
    
    # These should raise exceptions with closed session
    with pytest.raises(ResourceClosedError):
        record_api_request_success(db_session, year=2024, dist_id=1, status=1, office=1, record_count=50)
    
    # filter_api_request should return False on error
    result = filter_api_request(db_session, year=2024, dist_id=1, status=1, office=1)
    assert result is False
    
    with pytest.raises(Exception):
        mark_api_request_failed(db_session, year=2024, dist_id=1, status=1, office=1)

    