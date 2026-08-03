"""Tool adapters for provenance and official-source refresh."""

from services.campus_data_service import CampusDataService


def refresh_official_sources(campus: str | None = None, force: bool = False):
    return CampusDataService().refresh_official_sources(campus=campus, force=force)


def list_data_sources(campus: str | None = None):
    return CampusDataService().list_sources(campus)
