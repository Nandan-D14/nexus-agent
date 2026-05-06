from .health import router as health_router
from .beta import router as beta_router
from .ws import router as ws_router
from .auth import router as auth_router
from .skills import router as skills_router
from .integrations import router as integrations_router
from .files import router as files_router
from .templates import router as templates_router
from .sessions import router as sessions_router
from .users import router as users_router

__all__ = [
    "health_router",
    "beta_router",
    "ws_router",
    "auth_router",
    "skills_router",
    "integrations_router",
    "files_router",
    "templates_router",
    "sessions_router",
    "users_router",
]
