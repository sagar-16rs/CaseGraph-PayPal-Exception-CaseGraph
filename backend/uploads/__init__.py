"""Private evidence-file storage for security.

Keep package import side-effect free: importing validators/action helpers must not
require the full database-backed application tree. Runtime services are imported
from their concrete modules by API/action code.
"""

__all__: list[str] = []
