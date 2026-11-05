"""Typed sync and async clients for the public slip API."""

from .client import Client as Client, AsyncClient as AsyncClient
from .models import AccountType as AccountType, QrType as QrType
from ._codec import UNSET as UNSET
from ._base_error import SDKError as SDKError

__version__ = "0.0.0"  # x-release-please-version

from ._base_error import ThunderError as ThunderError

Thunder = Client
