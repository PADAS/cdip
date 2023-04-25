from pydantic import BaseModel
from typing import List, Union


# Selectors are modeled as pydantic models

class ListSelector(BaseModel):
    # Select specific devices by id
    ids: List[str]


class AreaSelector(BaseModel):
    # Select devices within a polygon representing a geographic area
    points: List[Point]


class SourceSelector(BaseModel):
    type: str
    configuration: Union[ListSelector, AreaSelector]
