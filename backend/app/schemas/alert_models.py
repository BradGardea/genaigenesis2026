from pydantic import BaseModel, Field
from typing import List, Optional

class AlertSignal(BaseModel):
    id: str
    signal_type: str = Field(description="Disaster type")
    value: str
    severity: str
    source: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    region: Optional[str] = None
    timestamp: Optional[str] = None

class GeoFeature(BaseModel):
    type: str = "Feature"
    geometry: dict = None
    properties: dict


class GeoFeatureCollection(BaseModel):
    type: str = "FeatureCollection"
    features: List[GeoFeature]