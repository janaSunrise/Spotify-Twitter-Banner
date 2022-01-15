import base64
import json
import sys
import time
import typing as t

import requests
from loguru import logger

from .route import Route
from ..config import Config
from ..utils import generate_oauth_url

PYTHON_VERSION = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"


class Spotify:
    RETRY_ATTEMPTS = 5
    USER_AGENT = f"Spotify Twitter Banner ({Config.GITHUB_REPO_URL}) - Python/{PYTHON_VERSION} Requests/{requests.__version__}"

    def __init__(self, client_id: str, client_secret: str) -> None:
        self.client_id = client_id
        self.client_secret = client_secret

        self.bearer_info = None
        self.refresh_token = self.load_refresh_token()

    # Get bearer info.
    def get_bearer_info(self) -> dict:
        if not self.refresh_token:
            raise Exception("No refresh token provided.")

        token = self.generate_base64_token()

        headers = {"Authorization": f"Basic {token}"}
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token
        }

        # Get the bearer info.
        response = requests.post("https://accounts.spotify.com/api/token", headers=headers, data=data)

        # Check if the request was successful.
        if response.status_code != 200:
            raise Exception("Failed to get bearer info.")

        # Return the bearer info.
        info = response.json()

        if "error" in info:
            raise Exception(f"Failed to get bearer info: {info['error']}")

        return info

    # Function to get the refresh token from code.
    def get_refresh_token(self, code: str) -> dict:
        token = self.generate_base64_token()

        # Headers and data.
        headers = {
            "Authorization": f"Basic {token}"
        }
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": Config.SPOTIFY_REDIRECT_URI,
        }

        # Post.
        response = requests.post("https://accounts.spotify.com/api/token", headers=headers, data=data)

        return response.json()

    # Function to handle loading refresh token.
    def load_refresh_token(self) -> str:
        # Load JSON and get refresh token.
        with open(Config.SPOTIFY_REFRESH_TOKEN_PATH, "r") as file:
            token = json.load(file)

        # Check if refresh token exists.
        if "refresh_token" not in token:
            logger.info("No refresh token found. Please follow the steps to get the refresh token.")

            # Generate OAuth URL.
            url = generate_oauth_url(self.client_id, Config.SPOTIFY_REDIRECT_URI, Config.SCOPES)
            print(f"Please visit the following URL to authorize the application: {url}")

            # Wait for user to input code.
            code = input("Enter the value of code from URL query parameter: ")

            # Handle input.
            if not code:
                raise Exception("No code provided.")

            # Get refresh token.
            token = self.get_refresh_token(code)

            # Calculate expired time
            expires_in = int(token["expires_in"])
            expires_at = time.time() + expires_in
            token["expires_at"] = expires_at

            # Save refresh token.
            with open(Config.SPOTIFY_REFRESH_TOKEN_PATH, "w") as file:
                json.dump(token, file)

        # Return refresh token.
        return token["refresh_token"]

    # Method to fetch the API.
    def fetch(self, route: Route, **kwargs) -> t.Optional[dict]:
        headers = kwargs.pop("headers", {})
        data = kwargs.pop("data", None)

        # Check if Authorization exists.
        if "Authorization" not in headers:
            # Check if bearer info exists.
            if self.bearer_info is None:
                self.bearer_info = self.get_bearer_info()

            # Set the Authorization header.
            headers["Authorization"] = f"Bearer {self.bearer_info['access_token']}"

        headers = {
            "User-Agent": self.USER_AGENT,
            **headers
        }

        # Perform request with retries.
        for _ in range(self.RETRY_ATTEMPTS):
            # Fetch.
            response = requests.request(route.method, route.url, headers=headers, json=data)

            # Log code.
            logger.debug(f"Fetch: [{route.method}] {route.url} | Code: {response.status_code}")

            # Check if the request was successful.
            if response.status_code == 200:
                return response.json()

            # Check if the request was a 429.
            if response.status_code == 429:
                # Get Retry-After header, and wait for it to clear.
                retry_after = int(response.headers["Retry-After"])

                # Wait for the Retry-After header to clear.
                logger.info(f"Ratelimited. Waiting for {retry_after} seconds.")
                time.sleep(retry_after)

                # Retry.
                continue

            # Check if the request was a 401.
            if response.status_code == 401:
                # Get the bearer info.
                logger.info("Bearer info expired. Refreshing.")
                self.bearer_info = self.get_bearer_info()

                # Retry.
                continue

            # Check if the request was a 404.
            if response.status_code == 404:
                # Return None.
                logger.warning(f"Failed to fetch: {route.url}. Route not found.")
                return None

            # Ignore anything 5xx
            if response.status_code >= 500:
                continue

    # Utility methods.
    def generate_base64_token(self) -> str:
        return base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode("utf-8")

    @staticmethod
    def _form_url(url: str, data: dict) -> str:
        url += "?" + "&".join([f"{dict_key}={dict_value}" for dict_key, dict_value in data.items()])

        return url

    # Currently playing.
    def currently_playing(self) -> t.Optional[dict]:
        route = Route("GET", "/me/player/currently-playing")

        return self.fetch(route)

    # Is playing?
    def is_playing(self) -> bool:
        return self.currently_playing() is not None and self.currently_playing()["is_playing"]

    # Recently played.
    def recently_played(
        self, limit: int = 20, before: t.Optional[str] = None, after: t.Optional[str] = None
    ) -> t.Optional[dict]:
        data = {"limit": limit}

        if before:
            data["before"] = before

        if after:
            data["after"] = after

        # Form the route
        route = Route(
            "GET",
            self._form_url("/me/player/recently-played", data)
        )

        return self.fetch(route)

    # Top songs.
    def top_tracks(
        self,
        limit: int = 20,
        offset: int = 0,
        time_range: t.Optional[t.Literal["short_term", "medium_term", "long_term"]] = None
    ) -> t.Optional[dict]:
        # Add URL parameters.
        data = {
            "limit": limit,
            "offset": offset
        }

        if time_range:
            data["time_range"] = time_range

        # Route.
        route = Route(
            "GET",
            self._form_url("/me/top/tracks", data)
        )

        return self.fetch(route)
