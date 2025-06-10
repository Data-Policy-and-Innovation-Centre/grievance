from pydantic import BaseModel
from typing import Optional
from loguru import logger

class District(BaseModel):
    """
    Pydantic model representing a district with its name and unique identifier.

    Attributes:
        distName (str): The name of the district.
        distId (int): The unique identifier for the district.
    """
    distName: str
    distId: int

class Complaint(BaseModel):
    pass

def validate(items: list[dict], model: BaseModel) -> dict:
    """
    Validates data against a Pydantic model.
    Args:
        items (list[dict]): The data to validate.
        model (BaseModel): The Pydantic model to validate against.
    Returns:
        dict: The validated data as a dictionary.
    Raises:
        ValueError: If the data does not match the expected format.
    """
    validated = []
    errors = []
    for idx, item in enumerate(items):
        try:
            validated.append(model(**item))
        except Exception as e:
            errors.append((idx, item, str(e)))
    if errors:
        error_msgs = "\n".join(
            [f"Index {idx}: {err}\nItem: {itm}" for idx, itm, err in errors]
        )
        logger.error(f"Validation failed for {len(errors)} records:\n{error_msgs}")
    return validated