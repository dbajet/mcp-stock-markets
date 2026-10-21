from __future__ import annotations

from mcp_stock_markets.commands.session_command import SessionCommand
from mcp_stock_markets.constants.auth_constants import AuthConstants
from mcp_stock_markets.constants.link_purpose import LinkPurpose
from mcp_stock_markets.libraries.email_box import EmailBox
from mcp_stock_markets.libraries.email_composer import EmailComposer
from mcp_stock_markets.libraries.job_queue import JobQueue
from mcp_stock_markets.libraries.magic_link_store import MagicLinkStore
from mcp_stock_markets.libraries.token_maker import TokenMaker
from mcp_stock_markets.libraries.user_store import UserStore
from mcp_stock_markets.structures.app_exception import AppException
from mcp_stock_markets.structures.settings import Settings


class SignInCommand:
    """Magic links: asked for by address, sent by email, spent once.

    A request does the same work for every address — it queues the address
    and answers — and the lookup and the email happen on the job thread, so
    neither the answer nor its timing says whether the address has an
    account. Only the owner's has one that is enabled (OwnerCommand)."""

    def __init__(
        self,
        settings: Settings,
        users: UserStore,
        links: MagicLinkStore,
        sessions: SessionCommand,
        composer: EmailComposer,
        email_box: EmailBox,
        jobs: JobQueue,
    ) -> None:
        self._settings = settings
        self._users = users
        self._links = links
        self._sessions = sessions
        self._composer = composer
        self._email_box = email_box
        self._jobs = jobs

    def requested(self, email: str) -> str:
        self._jobs.queued(self.delivered, (email,))
        return AuthConstants.link_requested

    def delivered(self, email: str) -> None:
        user = self._users.by_email(email)
        if user is None or user.is_disabled:
            return
        link = self._link(user.user_id, LinkPurpose.SIGN_IN, AuthConstants.magic_link_minutes)
        self._email_box.send(
            user.email,
            self._composer.sign_in_subject(),
            self._composer.sign_in_lines(user.display_name, link),
        )

    def redeemed(self, token: str) -> str:
        """A session token for the link's owner; the same refusal for a link
        that is unknown, expired, spent, or whose owner was disabled."""
        user_id = self._links.redeemed(TokenMaker.digest(token))
        user = None if user_id is None else self._users.by_id(user_id)
        if user is None or user.is_disabled:
            raise AppException(401, AuthConstants.link_refused)
        return self._sessions.started(user.user_id)

    def _link(self, user_id: int, purpose: LinkPurpose, minutes: int) -> str:
        token = TokenMaker.token()
        self._links.created(user_id, TokenMaker.digest(token), purpose, minutes)
        return f"{self._settings.app_base_url}{AuthConstants.link_path}?token={token}"
