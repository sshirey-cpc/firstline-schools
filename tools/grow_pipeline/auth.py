"""Authentication module for Grow API."""
import logging
import requests
from typing import Dict

logger = logging.getLogger(__name__)


class AuthenticationError(Exception):
    """Raised when authentication fails."""
    pass


def get_bearer_token(client_id: str, client_secret: str) -> str:
    """
    Obtain bearer token from Grow API using client credentials.

    Args:
        client_id: The client ID from environment variables
        client_secret: The client secret from environment variables

    Returns:
        Bearer token string

    Raises:
        AuthenticationError: If authentication fails
    """
    auth_url = "https://grow-api.leveldata.com/external/auth"

    # Try JSON body format first (most common for modern APIs)
    json_payload = {
        "client_id": client_id,
        "client_secret": client_secret,
    }

    logger.info("Attempting authentication with Grow API")

    try:
        response = requests.post(
            auth_url,
            json=json_payload,
            timeout=30,
            headers={"Content-Type": "application/json"}
        )

        # If JSON format worked
        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token") or data.get("token")
            if token:
                logger.info("Successfully authenticated with Grow API")
                return token
            else:
                raise AuthenticationError(
                    f"Authentication response missing token. Response: {data}"
                )

        # If JSON didn't work, try form data format
        if response.status_code in [400, 401, 415]:  # Bad request, Unauthorized, or Unsupported Media Type
            logger.info("JSON auth failed, trying form data format")
            form_payload = {
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            }

            response = requests.post(
                auth_url,
                data=form_payload,
                timeout=30,
            )

            if response.status_code == 200:
                data = response.json()
                token = data.get("access_token") or data.get("token")
                if token:
                    logger.info("Successfully authenticated with Grow API using form data")
                    return token
                else:
                    raise AuthenticationError(
                        f"Authentication response missing token. Response: {data}"
                    )

        # Authentication failed
        logger.error(
            f"Authentication failed with status {response.status_code}: {response.text}"
        )
        raise AuthenticationError(
            f"Failed to authenticate with Grow API. "
            f"Status: {response.status_code}, "
            f"Response: {response.text}\n"
            f"Please verify GROW_CLIENT_ID and GROW_CLIENT_SECRET in .env file."
        )

    except requests.exceptions.RequestException as e:
        logger.error(f"Network error during authentication: {str(e)}")
        raise AuthenticationError(f"Network error during authentication: {str(e)}")
