"""Project-specific prototype assumptions, kept outside generic models."""

from dataclasses import dataclass

from .models import PlanningConfig


@dataclass(frozen=True, slots=True)
class PrototypeLocation:
    """Descriptive metadata only; this is not a geocoded road node."""

    node_id: str
    name: str
    description: str
    address: str
    vehicle_access_confirmed: bool = False


KVA_BASEL = PrototypeLocation(
    node_id="kva-basel",
    name="KVA Basel",
    description="General-waste incineration plant",
    address="Hagenaustrasse 40, 4056 Basel",
)


def prototype_configuration(
    *,
    truck_capacity: float,
    demand_unit: str,
    yellow_threshold: float,
    red_threshold: float,
) -> PlanningConfig:
    """Build the documented prototype configuration with a round trip.

    Thresholds and capacity remain caller-supplied because no operational
    values were verified during Stage 0.
    """

    return PlanningConfig(
        start_node_id=KVA_BASEL.node_id,
        end_node_id=KVA_BASEL.node_id,
        truck_capacity=truck_capacity,
        demand_unit=demand_unit,
        yellow_threshold=yellow_threshold,
        red_threshold=red_threshold,
    )
