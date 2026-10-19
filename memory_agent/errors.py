class ApiError(Exception):
    status = 400
    type = "ValidationException"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class BadRequest(ApiError):
    pass


class Unauthorized(ApiError):
    status = 401
    type = "UnrecognizedClientException"


class AccessDenied(ApiError):
    status = 403
    type = "AccessDeniedException"


class NotFound(ApiError):
    status = 404
    type = "ResourceNotFoundException"


class Conflict(ApiError):
    status = 409
    type = "ConflictException"
