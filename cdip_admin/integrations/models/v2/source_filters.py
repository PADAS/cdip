from pydantic import BaseModel
from typing import List, Union


# Filters are modeled as pydantic models

class ListFilter(BaseModel):
    # Select specific devices by id
    ids: List[str]


class GEOFilter(BaseModel):
    # Select devices within a polygon representing a geographic area
    points: List[Point]


class SourceSelector(BaseModel):
    type: str
    configuration: Union[ListFilter, GEOFilter]
