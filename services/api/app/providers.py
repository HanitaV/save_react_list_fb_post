import csv
import io
import json
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from urllib.parse import urlsplit

from pydantic import BaseModel, field_validator

from .identity import canonical_post_url, normalize_identifier
from .models import InteractionType


class InteractionRow(BaseModel):
    post_url: str
    profile_url: str
    display_name: str | None = None
    reaction_type: InteractionType
    observed_at: datetime

    @field_validator("observed_at")
    @classmethod
    def observed_at_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at needs a timezone offset")
        return value.astimezone(timezone.utc)

    @field_validator("post_url")
    @classmethod
    def post_url_valid(cls, value: str) -> str:
        return canonical_post_url(value)

    @field_validator("profile_url")
    @classmethod
    def profile_url_valid(cls, value: str) -> str:
        parts = urlsplit(value)
        if parts.scheme != "https" or not parts.netloc:
            raise ValueError("Profile must be an HTTPS Facebook URL")
        normalize_identifier(value)
        return value.strip()


class InteractionProvider(ABC):
    @abstractmethod
    def validate_source(self, content: str) -> None: ...

    @abstractmethod
    def fetch_post_metadata(self, content: str) -> dict: ...

    @abstractmethod
    def fetch_interactions(self, content: str) -> list[InteractionRow]: ...


class ManualCSVProvider(InteractionProvider):
    def validate_source(self, content: str) -> None:
        header = set(next(csv.reader(io.StringIO(content)), []))
        if not {"post_url", "profile_url", "reaction_type", "observed_at"} <= header:
            raise ValueError(
                "CSV needs post_url, profile_url, reaction_type, observed_at"
            )

    def fetch_post_metadata(self, content: str) -> dict:
        return {"source": "manual_csv"}

    def fetch_interactions(self, content: str) -> list[InteractionRow]:
        self.validate_source(content)
        return [
            InteractionRow.model_validate(row)
            for row in csv.DictReader(io.StringIO(content))
        ]


class JSONImportProvider(InteractionProvider):
    def validate_source(self, content: str) -> None:
        if not isinstance(json.loads(content), list):
            raise TypeError("JSON import needs an array")

    def fetch_post_metadata(self, content: str) -> dict:
        return {"source": "json_import"}

    def fetch_interactions(self, content: str) -> list[InteractionRow]:
        self.validate_source(content)
        return [InteractionRow.model_validate(row) for row in json.loads(content)]


class ExtensionBundleProvider(InteractionProvider):
    """Import extension scans without treating scan time as reaction time."""

    REACTIONS = {
        "like": "LIKE",
        "thích": "LIKE",
        "love": "LOVE",
        "yêu thích": "LOVE",
        "haha": "HAHA",
        "wow": "WOW",
        "sad": "SAD",
        "buồn": "SAD",
        "angry": "ANGRY",
        "phẫn nộ": "ANGRY",
        "care": "CARE",
        "thương thương": "CARE",
    }

    def validate_source(self, content: str) -> None:
        payload = json.loads(content)
        if not isinstance(payload, dict) or not isinstance(payload.get("scans"), list):
            raise ValueError("Extension bundle needs a scans array")
        if any(not isinstance(scan, dict) for scan in payload["scans"]):
            raise ValueError("Every scan must be an object")

    def fetch_post_metadata(self, content: str) -> dict:
        self.validate_source(content)
        scans = json.loads(content)["scans"]
        return {
            "source": "extension_scan",
            "scans": len(scans),
            "truncated_scans": sum(bool(scan.get("truncated")) for scan in scans),
        }

    def fetch_interactions(self, content: str) -> list[InteractionRow]:
        self.validate_source(content)
        rows = []
        for scan in json.loads(content)["scans"]:
            if not isinstance(scan, dict) or not isinstance(scan.get("records"), list):
                raise ValueError("Every scan needs a records array")
            for record in scan["records"]:
                if not isinstance(record, dict):
                    raise ValueError("Every record must be an object")
                reaction = str(record.get("reaction") or "").strip().casefold()
                rows.append(
                    InteractionRow(
                        post_url=scan.get("post_url"),
                        profile_url=record.get("profile_url"),
                        display_name=record.get("name"),
                        reaction_type=self.REACTIONS.get(reaction, "OTHER"),
                        # This is the scan timestamp. Analysis excludes extension_scan
                        # rows from reaction burst detection.
                        observed_at=scan.get("captured_at"),
                    )
                )
        return rows


class AuthorizedFacebookProvider(InteractionProvider):
    def validate_source(self, content: str) -> None:
        raise RuntimeError("Configure an authorized data integration before use")

    def fetch_post_metadata(self, content: str) -> dict:
        self.validate_source(content)
        return {}

    def fetch_interactions(self, content: str) -> list[InteractionRow]:
        self.validate_source(content)
        return []
