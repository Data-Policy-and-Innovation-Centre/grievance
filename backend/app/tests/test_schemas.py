import sys
from datetime import datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.ingestion.schemas import Complaint, District, validate

# Mock OFFICE and settings for testing

OFFICE = {"1": "Office A", "2": "Office B"}
sys.modules["app.ingestion.schemas"].OFFICE = OFFICE

settings = SimpleNamespace(DEBUG=True)
sys.modules["app.ingestion.schemas"].settings = settings


def valid_complaint_dict(**overrides):
    data = {
        "ticketNumber": "T123",
        "petitionerName": "John Doe",
        "petitionerMobile": "1234567890",
        "petitionerEmail": "john@example.com",
        "grievanceSubject": "Road issue",
        "Document": "www.example.com",
        "intOfficeId": 1,
        "officeNAme": "Office A",
        "RecievedByOfficerName": "Officer X",
        "intDistId": 1,
        "districtName": "District 1",
        "intBlockId": 1,
        "blockName": "Block A",
        "Address": "123 Main St",
        "modeName": "Online",
        "disbilityName": None,
        "StatusName": "Pending",
        "govtTicket": "Yes",
        "CreatedOn": "2024-06-01T12:00:00",
        "taggedTo": None,
        "taggedByName": None,
        "taggedDate": None,
        "CategoryId": 1,
        "category": "Infrastructure",
        "DepartmentId": 1,
        "deptName": "PWD",
        "SubCategoryId": 1,
        "Subcategory": "Road",
        "stateName": "StateX",
        "genderName": "Male",
        "transferStatus": "None",
        "mostUrgent": "No",
        "pendingwithName": None,
        "assignedOn": "2024-06-01T13:00:00",
        "escalationDate": None,
        "isSelfAssign": "No",
        "ResolvedOn": None,
        "resolvedBy": "Officer Y",
        "benefitted": "No",
        "trackingId": "track-123",
        "reviewAuthority": None,
        "reviewAuthorityName": None,
        "vchAllEscUser": None,
        "reopenedBy": None,
        "vchAccount": None,
    }
    data.update(overrides)
    return data


def test_district_model():
    d = District(distName="District X", distId=1)
    assert d.dist_name == "District X"
    assert d.dist_id == 1


def test_complaint_valid_data():
    data = valid_complaint_dict()
    c = Complaint(**data)
    assert c.ticket_no == "T123"
    assert c.office == "Office A"
    assert c.govt_ticket is True
    assert isinstance(c.created_on, datetime)
    assert c.status == "Pending"


def test_complaint_office_typo_correction(monkeypatch):
    # Simulate typo in office name, should match closest
    data = valid_complaint_dict(officeNAme="Office B")
    c = Complaint(**data)
    assert c.office == "Office B"


def test_complaint_office_invalid():
    data = valid_complaint_dict(officeNAme="Unknown Office")
    with pytest.raises(ValidationError) as exc:
        Complaint(**data)
    assert "is not recognized" in str(exc.value)


@pytest.mark.parametrize(
    "input_val,expected",
    [
        ("Yes", True),
        ("No", False),
        ("yes", True),
        ("no", False),
    ],
)
def test_complaint_govt_ticket_variants(input_val, expected):
    data = valid_complaint_dict(govtTicket=input_val)
    c = Complaint(**data)
    assert c.govt_ticket is expected


def test_complaint_govt_ticket_invalid():
    data = valid_complaint_dict(govtTicket="Maybe")
    with pytest.raises(ValidationError) as exc:
        Complaint(**data)
    assert "not recognized" in str(exc.value)


def test_complaint_datetime_formats():
    data = valid_complaint_dict(CreatedOn="2024-06-01T12:00:00")
    c = Complaint(**data)
    assert isinstance(c.created_on, datetime)

    data2 = valid_complaint_dict(
        CreatedOn="2024-06-01T12:00:00", assignedOn="2024-06-01T13:00:00"
    )
    c2 = Complaint(**data2)
    assert isinstance(c2.assigned_on, datetime)


def test_complaint_datetime_invalid():
    data = valid_complaint_dict(CreatedOn="not-a-date")
    with pytest.raises(ValidationError) as exc:
        Complaint(**data)
    assert (
        "input should be a valid datetime" in str(exc.value).lower()
        or "parse datetime" in str(exc.value).lower()
    )


def test_validate_function_success(monkeypatch):
    # Patch logger to avoid actual logging
    monkeypatch.setattr(
        "app.ingestion.schemas.logger",
        SimpleNamespace(
            info=lambda *a, **k: None,
            debug=lambda *a, **k: None,
            error=lambda *a, **k: None,
        ),
    )
    items = [valid_complaint_dict()]
    validated = validate(items, Complaint, dict_mode=False)
    assert len(validated) == 1
    assert isinstance(validated[0], Complaint)

    validated_dict = validate(items, Complaint, dict_mode=True)
    assert len(validated_dict) == 1
    assert isinstance(validated_dict[0], dict)
    assert validated_dict[0]["ticket_no"] == "T123"


def test_validate_function_with_errors(monkeypatch):
    monkeypatch.setattr(
        "app.ingestion.schemas.logger",
        SimpleNamespace(
            info=lambda *a, **k: None,
            debug=lambda *a, **k: None,
            error=lambda *a, **k: None,
        ),
    )
    items = [valid_complaint_dict(), valid_complaint_dict(officeNAme="Unknown Office")]
    validated = validate(items, Complaint)
    assert len(validated) == 1  # Only the valid one is returned
