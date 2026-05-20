"""SmartIO session presentation helpers for MainWindow."""

from __future__ import annotations

from dataclasses import dataclass

from runtime.application import AppMode


@dataclass(slots=True, frozen=True)
class RuntimeConnectionPresentation:
    """Presentation tokens for runtime connection badge/label."""

    visible: bool
    normalized_status: str
    state_key: str
    badge_style: str


class SmartIOSessionAdapter:
    """Converts SmartIO status tokens to UI-facing presentation values."""

    _DEFAULT_BADGE_STYLE = "background:#8b949e; border:1px solid #6e7781;"
    _BADGE_STYLES: dict[str, str] = {
        "connected": "background:#23a55a; border:1px solid #1b7f46;",
        "connecting": "background:#2f6feb; border:1px solid #2456b7;",
        "reconnecting": "background:#d29922; border:1px solid #9f7218;",
        "error": "background:#da3633; border:1px solid #a92c2a;",
        "disabled": "background:#8b949e; border:1px solid #6e7781;",
        "disconnected": "background:#8b949e; border:1px solid #6e7781;",
    }

    @classmethod
    def presentation(
        cls,
        *,
        operating_mode: AppMode,
        status_token: str,
    ) -> RuntimeConnectionPresentation:
        raw_token = str(status_token or "").strip().lower()
        visible = operating_mode is AppMode.RUNTIME
        normalized = cls._normalize_status_token(raw_token)
        state_key = cls._state_key_for_token(raw_token)
        badge_style = cls._BADGE_STYLES.get(normalized, cls._DEFAULT_BADGE_STYLE)
        return RuntimeConnectionPresentation(
            visible=visible,
            normalized_status=normalized,
            state_key=state_key,
            badge_style=badge_style,
        )

    @staticmethod
    def _normalize_status_token(token: str) -> str:
        if token.startswith("reconnecting_in_"):
            return "reconnecting"
        if token:
            return token
        return "disconnected"

    @staticmethod
    def _state_key_for_token(token: str) -> str:
        if token.startswith("reconnecting_in_"):
            return "smartio.state.reconnecting"
        if token == "connected":
            return "smartio.state.connected"
        if token == "connecting":
            return "smartio.state.connecting"
        if token == "error":
            return "smartio.state.error"
        if token == "disabled":
            return "smartio.state.disabled"
        return "smartio.state.disconnected"
