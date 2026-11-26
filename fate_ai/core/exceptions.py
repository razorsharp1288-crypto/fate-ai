class FateError(Exception):
    """Base class for all FATE AI errors. Messages are safe to show users."""


class ProviderError(FateError):
    pass


class AuthenticationError(ProviderError):
    pass


class RateLimitError(ProviderError):
    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class ProviderUnavailableError(ProviderError):
    pass


class CredentialError(FateError):
    pass


class SandboxError(FateError):
    pass


class VirtualizationError(FateError):
    pass


class BackendUnavailableError(VirtualizationError):
    pass


class PermissionDeniedError(FateError):
    pass


class ValidationError(FateError):
    pass


class ResourceLimitError(FateError):
    pass
