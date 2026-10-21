from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import exceptions, serializers
from rest_framework.views import exception_handler as drf_exception_handler


class BusinessRuleError(Exception):
    """Raised by service-layer code when a business/policy rule is violated."""

    def __init__(self, message, code="business_rule"):
        super().__init__(message)
        self.message = message
        self.code = code


def exception_handler(exc, context):
    if isinstance(exc, BusinessRuleError):
        exc = serializers.ValidationError({"detail": exc.message, "code": exc.code})
    elif isinstance(exc, DjangoValidationError):
        detail = exc.message_dict if hasattr(exc, "error_dict") else {"detail": exc.messages}
        exc = serializers.ValidationError(detail)
    elif isinstance(exc, ObjectDoesNotExist):
        # a missing id - or another organization's, hidden by the tenant filter - is a 404, never a 500
        exc = exceptions.NotFound()
    return drf_exception_handler(exc, context)
