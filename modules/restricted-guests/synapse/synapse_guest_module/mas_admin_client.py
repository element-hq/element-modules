# Copyright 2025 New Vector Ltd.
#
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Element-Commercial
# Please see LICENSE files in the project root for full details.

import base64
import logging
import random
import string
from datetime import datetime
from typing import Any, Optional

import attr
from synapse.module_api import ModuleApi

from synapse_guest_module.config import MasConfig

logger = logging.getLogger("synapse.contrib." + __name__)


@attr.s(frozen=True, auto_attribs=True)
class RegistrationToken:
    id: str
    invite_url: str


class MasAdminClient:
    def __init__(self, api: ModuleApi, config: MasConfig):
        self._api = api
        self._config = config
        # Strip any trailing slashes if present
        self._admin_api_base_url = config.admin_api_base_url.rstrip("/")
        self._oauth_base_url = config.oauth_base_url.rstrip("/")
        self._client_secret = self._load_client_secret()

    async def create_user(self, username: str) -> str:
        """Creates a new user in MAS with the given username.

        Args:
            username: The username (localpart) of the user to create.

        Returns:
            The MAS ID of the created user.
        """
        token = await self.request_admin_token()
        url = self._build_admin_url("/api/admin/v1/users")

        response = await self._api.http_client.post_json_get_json(
            uri=url,
            post_json={"username": username},
            headers={"Authorization": [f"Bearer {token}"]},
        )

        mas_user_id: str = response.get("data", {}).get("id")
        if mas_user_id is None or not isinstance(mas_user_id, str):
            raise ValueError("MAS user creation response missing `data.id` field")

        return mas_user_id

    async def create_personal_session(
        self, mas_user_id: str, expires_in_sec: int
    ) -> tuple[str, str]:
        """Creates a new personal session for the given MAS user.

        Args:
            mas_user_id: The MAS user ID.
            expires_in_sec: The session expiration time in seconds.

        Returns:
            A tuple of (device_id, access_token).
        """
        token = await self.request_admin_token()
        url = self._build_admin_url("/api/admin/v1/personal-sessions")

        device_id = self._generate_device_id()
        request_body = {
            "actor_user_id": mas_user_id,
            "expires_in": expires_in_sec,
            "scope": f"openid urn:matrix:client:api:* urn:matrix:client:device:{device_id}",
            "human_name": "guest session",
        }

        response = await self._api.http_client.post_json_get_json(
            uri=url,
            post_json=request_body,
            headers={"Authorization": [f"Bearer {token}"]},
        )

        data = response.get("data", {})
        attributes = data.get("attributes", {}) if isinstance(data, dict) else {}
        access_token = attributes.get("access_token")

        if not isinstance(access_token, str) or len(access_token) == 0:
            raise ValueError("MAS session response missing `access_token` field")

        return device_id, access_token

    async def create_registration_token(
        self,
        username: str,
        room_id: str,
        token: str,
        email: Optional[str] = None,
        usage_limit: Optional[int] = None,
        expires_at: Optional[datetime] = None,
    ) -> RegistrationToken:
        """Has MAS mint a passwordless invite code for the room.

        Args:
            username: The username, or username template, its users register with.
            room_id: The room its users are sent to once registered.
            token: An admin access token from `request_admin_token`.
            email: The address the invite code is pinned to, if any.
            usage_limit: How many times it can be used, if limited.
            expires_at: When it expires, timezone-aware, if it does.

        Raises:
            ValueError: If the response has no `data.id` or `invite_url`.
            HttpResponseException: On a non-2xx HTTP response.
        """
        body: dict[str, Any] = {
            "username": username,
            "passwordless": True,
            "room_id": room_id,
            "email": email,
            "usage_limit": usage_limit,
            "expires_at": expires_at.isoformat() if expires_at is not None else None,
        }
        response = await self._api.http_client.post_json_get_json(
            uri=self._build_admin_url("/api/admin/v1/user-registration-tokens"),
            post_json={key: value for key, value in body.items() if value is not None},
            headers={"Authorization": [f"Bearer {token}"]},
        )

        data = response.get("data")
        token_id = data.get("id") if isinstance(data, dict) else None
        attributes = data.get("attributes") if isinstance(data, dict) else None
        invite_url = (
            attributes.get("invite_url") if isinstance(attributes, dict) else None
        )
        if not isinstance(token_id, str) or not isinstance(invite_url, str):
            raise ValueError(
                "MAS registration token response missing `data.id` or `invite_url`"
            )

        return RegistrationToken(token_id, invite_url)

    async def send_invite_emails(
        self,
        token_ids: list[str],
        room_name: Optional[str],
        inviter: str,
        inviter_name: Optional[str],
        token: str,
    ) -> int:
        """Has MAS email each invite code's link to the address it is pinned to.

        Args:
            token_ids: The IDs of the invite codes to send.
            room_name: The room's name, if it has one.
            inviter: The Matrix ID of the user inviting them.
            inviter_name: The inviter's display name in the room, if they have one.
            token: An admin access token from `request_admin_token`.

        Returns:
            How many emails MAS scheduled.

        Raises:
            ValueError: If the response has no `scheduled` count.
            HttpResponseException: On a non-2xx HTTP response.
        """
        body: dict[str, Any] = {
            "invites": [{"registration_token_id": token_id} for token_id in token_ids],
            "room_name": room_name,
            "inviter": inviter,
            "inviter_name": inviter_name,
        }
        response = await self._api.http_client.post_json_get_json(
            uri=self._build_admin_url(
                "/api/admin/v1/user-registration-tokens/invite-emails"
            ),
            post_json={key: value for key, value in body.items() if value is not None},
            headers={"Authorization": [f"Bearer {token}"]},
        )

        scheduled = response.get("scheduled")
        if not isinstance(scheduled, int):
            raise ValueError("MAS invite emails response missing `scheduled` field")

        return scheduled

    async def deactivate_user(self, mas_user_id: str, token: str | None = None) -> None:
        if token is None:
            token = await self.request_admin_token()

        url = self._build_admin_url(f"/api/admin/v1/users/{mas_user_id}/deactivate")
        await self._api.http_client.post_json_get_json(
            uri=url,
            post_json={"skip_erase": True},
            headers={"Authorization": [f"Bearer {token}"]},
        )

    async def request_admin_token(self) -> str:
        """
        Uses the client credentials flow to request an admin access token
        from MAS.

        Returns:
            The admin access token.

        Raises:
            ValueError: If the token response is invalid.
            HttpResponseException: On a non-2xx HTTP response.
        """
        url = self._build_oauth_url("/oauth2/token")
        basic_auth = base64.b64encode(
            f"{self._config.client_id}:{self._client_secret}".encode("utf-8")
        ).decode("ascii")
        headers = {
            "Authorization": [f"Basic {basic_auth}"],
            "Content-Type": ["application/x-www-form-urlencoded"],
        }
        data = {
            "grant_type": "client_credentials",
            "scope": "urn:mas:admin",
        }

        response = await self._api.http_client.post_urlencoded_get_json(
            url, data, headers
        )
        access_token = response.get("access_token")
        if not isinstance(access_token, str) or len(access_token) == 0:
            raise ValueError("MAS token response missing access_token")
        return access_token

    def _load_client_secret(self) -> str:
        """Source the MAS client secret from either configuration or a file."""
        if self._config.client_secret_filepath is not None:
            try:
                with open(
                    self._config.client_secret_filepath, "r", encoding="utf-8"
                ) as secret_file:
                    client_secret = secret_file.read().strip()
            except Exception as err:
                raise ValueError(
                    f"Failed to read MAS client secret file: {err}"
                ) from err

            if len(client_secret) == 0:
                raise ValueError("MAS client secret file is empty")

            return client_secret

        if self._config.client_secret is None:
            raise ValueError("MAS client secret is not configured")

        client_secret = self._config.client_secret.strip()
        if len(client_secret) == 0:
            raise ValueError("MAS client secret is empty")

        return client_secret

    @staticmethod
    def _generate_device_id() -> str:
        """Generate a MAS device ID.

        Device IDs must be at least 10 characters long and contain only
        [A-Za-z0-9-].

        The generated device ID is purposefully non-cryptographically random,
        as the value is public.

        Returns:
            The generated Device ID.
        """
        length = 16
        alphabet = string.ascii_letters + string.digits + "-"
        return "".join(random.choices(alphabet, k=length))

    def _build_admin_url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return f"{self._admin_api_base_url}{path}"

    def _build_oauth_url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return f"{self._oauth_base_url}{path}"
