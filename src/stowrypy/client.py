import hashlib
import hmac
import time
from typing import Literal
from urllib.parse import urlencode


class StowryClient:
    """Client for generating Stowry presigned URLs."""

    MIN_EXPIRES = 1
    MAX_EXPIRES = 604800

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
    ) -> None:
        """
        Initialize a Stowry client.

        Args:
            endpoint: Stowry server URL (e.g., "http://localhost:5708")
            access_key: Access key ID
            secret_key: Secret access key
        """
        self.endpoint = endpoint.rstrip("/")
        self.access_key = access_key
        self.secret_key = secret_key

    def _sign(self, method: str, path: str, timestamp: int, expires: int) -> str:
        string_to_sign = f"{method}\n{path}\n{timestamp}\n{expires}"
        return hmac.new(
            self.secret_key.encode(),
            string_to_sign.encode(),
            hashlib.sha256,
        ).hexdigest()

    def _presign(
        self, method: str, path: str, expires: int, timestamp: int | None = None
    ) -> str:
        if not path.startswith("/"):
            raise ValueError("Path must start with '/'")
        if not self.MIN_EXPIRES <= expires <= self.MAX_EXPIRES:
            raise ValueError(
                f"Expires must be between {self.MIN_EXPIRES} and {self.MAX_EXPIRES} seconds"
            )

        if timestamp is None:
            timestamp = int(time.time())

        signature = self._sign(method, path, timestamp, expires)

        query = urlencode(
            {
                "X-Stowry-Credential": self.access_key,
                "X-Stowry-Date": timestamp,
                "X-Stowry-Expires": expires,
                "X-Stowry-Signature": signature,
            }
        )

        return f"{self.endpoint}{path}?{query}"

    def presign_get(self, path: str, expires: int = 900) -> str:
        """
        Generate a presigned URL for GET requests.

        Args:
            path: Object path (e.g., "/files/document.pdf")
            expires: URL validity in seconds (default: 900, max: 604800)

        Returns:
            Presigned URL string
        """
        return self._presign("GET", path, expires)

    def presign_put(self, path: str, expires: int = 900) -> str:
        """
        Generate a presigned URL for PUT requests.

        Args:
            path: Object path (e.g., "/files/document.pdf")
            expires: URL validity in seconds (default: 900, max: 604800)

        Returns:
            Presigned URL string
        """
        return self._presign("PUT", path, expires)

    def presign_delete(self, path: str, expires: int = 900) -> str:
        """
        Generate a presigned URL for DELETE requests.

        Args:
            path: Object path (e.g., "/files/document.pdf")
            expires: URL validity in seconds (default: 900, max: 604800)

        Returns:
            Presigned URL string
        """
        return self._presign("DELETE", path, expires)

    def generate_presigned_url(
        self,
        operation: Literal["get_object", "put_object", "delete_object"],
        path: str,
        expires: int = 900,
    ) -> str:
        """
        Generate a presigned URL (S3-compatible interface).

        Args:
            operation: The operation ("get_object", "put_object", "delete_object")
            path: Object path (e.g., "/files/document.pdf")
            expires: URL validity in seconds (default: 900, max: 604800)

        Returns:
            Presigned URL string
        """
        methods = {
            "get_object": "GET",
            "put_object": "PUT",
            "delete_object": "DELETE",
        }
        return self._presign(methods[operation], path, expires)
