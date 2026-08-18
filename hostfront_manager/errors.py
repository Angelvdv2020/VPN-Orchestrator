class ManagerError(Exception):
    """Базовая ожидаемая ошибка Manager."""


class ConfigError(ManagerError):
    """Ошибка конфигурации."""


class CommandError(ManagerError):
    """Ошибка внешней команды."""


class LockError(ManagerError):
    """Не удалось получить блокировку Manager."""


class BackupError(ManagerError):
    """Ошибка backup/rollback."""


class ValidationError(ManagerError):
    """Проверка результата не прошла."""


class RemoteDeployError(ManagerError):
    """Ошибка удалённого развёртывания ноды."""


class ApiMutationError(ManagerError):
    """Ошибка изменения состояния через Remnawave API."""
