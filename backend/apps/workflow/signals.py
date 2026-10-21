"""Import workflow handlers from every domain app so they register with the engine."""

from apps.attendance import workflow_handlers as _attendance  # noqa: F401
from apps.compensation import workflow_handlers as _compensation  # noqa: F401
from apps.documents import workflow_handlers as _documents  # noqa: F401
from apps.employees import workflow_handlers as _employees  # noqa: F401
from apps.expenses import workflow_handlers as _expenses  # noqa: F401
from apps.learning import workflow_handlers as _learning  # noqa: F401
from apps.leave import workflow_handlers as _leave  # noqa: F401
from apps.offboarding import workflow_handlers as _offboarding  # noqa: F401
from apps.onboarding import workflow_handlers as _onboarding  # noqa: F401
from apps.payroll import workflow_handlers as _payroll  # noqa: F401
from apps.performance import workflow_handlers as _performance  # noqa: F401
from apps.recruitment import workflow_handlers as _recruitment  # noqa: F401
from apps.relations import workflow_handlers as _relations  # noqa: F401
