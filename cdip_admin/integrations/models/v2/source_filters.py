from pydantic import BaseModel
from typing import List, Union


# Filters modeled as pydantic models

class ListFilter(BaseModel):
    # Select specific devices by id
    ids: List[str]


class Point(BaseModel):
    lat: float
    lon: float


class GEOBoundaryFilter(BaseModel):
    # Select devices within a polygon representing a geographic area
    points: List[Point]

