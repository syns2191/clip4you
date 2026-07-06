"""Central store for connected social platform accounts and their tokens."""

import json
import os
from dataclasses import dataclass, field, asdict
from typing import Optional

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
_STORE_FILE = os.path.join(_ROOT, "integrations.json")


@dataclass
class ConnectedAccount:
    platform: str
    account_id: str
    display_name: str
    token: dict = field(default_factory=dict)
    extra: dict = field(default_factory=dict)


class IntegrationManager:
    def __init__(self):
        self._accounts: list[ConnectedAccount] = []
        self._load()

    def _load(self):
        if not os.path.exists(_STORE_FILE):
            return
        try:
            with open(_STORE_FILE) as f:
                raw = json.load(f)
            self._accounts = [ConnectedAccount(**a) for a in raw]
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            print(f"[integrations] Warning: failed to load {_STORE_FILE}: {e}")
            self._accounts = []

    def _save(self):
        tmp = _STORE_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump([asdict(a) for a in self._accounts], f, indent=2)
        os.replace(tmp, _STORE_FILE)  # atomic write — no partial files

    def all(self) -> list[ConnectedAccount]:
        return list(self._accounts)

    def for_platform(self, platform: str) -> list[ConnectedAccount]:
        return [a for a in self._accounts if a.platform == platform]

    def get(self, platform: str, account_id: str) -> Optional[ConnectedAccount]:
        return next(
            (a for a in self._accounts if a.platform == platform and a.account_id == account_id),
            None,
        )

    def upsert(self, account: ConnectedAccount):
        for i, a in enumerate(self._accounts):
            if a.platform == account.platform and a.account_id == account.account_id:
                self._accounts[i] = account
                self._save()
                return
        self._accounts.append(account)
        self._save()

    def remove(self, platform: str, account_id: str):
        self._accounts = [
            a for a in self._accounts
            if not (a.platform == platform and a.account_id == account_id)
        ]
        self._save()

    def choices_for(self, platform: str) -> list[str]:
        return [f"{a.display_name} ({a.account_id})" for a in self.for_platform(platform)]


_manager: Optional[IntegrationManager] = None


def get_manager() -> IntegrationManager:
    global _manager
    if _manager is None:
        _manager = IntegrationManager()
    return _manager
