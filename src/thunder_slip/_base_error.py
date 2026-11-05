"""Root error for this distribution."""


class ThunderError(Exception):
    """Base class for API and transport failures."""


SDKError = ThunderError
