import ipaddress
import re
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field, model_validator


class RouteInput(BaseModel):
    target_type: Literal["product", "category"]
    target_id: UUID


class StationInput(BaseModel):
    shop_id: UUID
    branch_id: UUID
    device_id: UUID
    name: str = Field(min_length=1, max_length=80)
    purpose: Literal["receipt", "kitchen", "bar"] = "receipt"
    transport: Literal["bluetooth", "usb", "network", "system"] = "system"
    address: str = Field(default="", max_length=180)
    paper_width: Literal["58mm", "80mm"] = "80mm"
    auto_print: bool = False
    active: bool = True
    routes: list[RouteInput] = Field(default_factory=list, max_length=300)

    @model_validator(mode="after")
    def validate_transport(self):
        self.name = self.name.strip()
        if not self.name or any(ord(c) < 32 for c in self.name):
            raise ValueError("Use a printable station name")
        if self.transport == "network":
            # Local Android transport only; never let a cloud worker perform SSRF.
            try:
                host, port = self.address.split(":")
                ip = ipaddress.IPv4Address(host)
                allowed = any(ip in block for block in map(ipaddress.ip_network, ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")))
                if not allowed or int(port) != 9100:
                    raise ValueError()
            except ValueError:
                raise ValueError("Use a private LAN IPv4 address and port 9100") from None
        if self.transport == "bluetooth" and not re.fullmatch(r"[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}", self.address):
            raise ValueError("Select a paired Bluetooth MAC address")
        if self.transport == "usb" and not re.fullmatch(r"[A-Za-z0-9/_:.-]{1,180}", self.address):
            raise ValueError("Select an authorized USB device")
        return self


class JobInput(BaseModel):
    sale_id: UUID | None = None
    kind: Literal["receipt", "kot", "test"] = "receipt"
    request_key: str = Field(min_length=1, max_length=120)
    reprint: bool = False
    table: str = Field(default="", max_length=60)
    notes: str = Field(default="", max_length=500)
    item_notes: dict[UUID, str] = Field(default_factory=dict, max_length=200)
    manager_authorization: str | None = None


class ClaimInput(BaseModel):
    token: str = Field(min_length=32, max_length=120)


class ResultInput(ClaimInput):
    outcome: Literal["submitted", "uncertain"]
    error: str = Field(default="", max_length=240)


class RetryInput(BaseModel):
    reason: str = Field(min_length=5, max_length=240)
    manager_authorization: str | None = None


class OfflineReviewInput(BaseModel):
    reason: str = Field(min_length=5, max_length=240)
    decision: Literal["already_printed", "printed_manually", "not_required"]
