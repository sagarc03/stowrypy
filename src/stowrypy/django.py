import os
import pathlib
import posixpath
import shutil
import tempfile
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, SuspiciousFileOperation
from django.core.files.base import File
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible

from stowrypy.client import StowryClient


def _setting(name: str, default: Any = None) -> Any:
    """Read a Django setting with a fallback default.

    Args:
        name: Setting name, e.g. ``"STOWRY_ENDPOINT"``.
        default: Value to return when the setting is absent.

    Returns:
        The value from Django settings, or *default*.
    """
    return getattr(settings, name, default)


def _clean_name(name: str | pathlib.PurePath) -> str:
    """Normalize a file name/path for storage.

    Handles ``pathlib.PurePath`` objects, Windows-style backslashes, and
    ``..`` segments.  Preserves trailing slashes.

    Args:
        name: The raw file name or path.

    Returns:
        A cleaned, forward-slash-separated path string.
    """
    if isinstance(name, pathlib.PurePath):
        name = str(name)
    clean = posixpath.normpath(name).replace("\\", "/")
    # posixpath.normpath strips trailing slashes; restore if present.
    if name.endswith("/") and not clean.endswith("/"):
        clean += "/"
    # normpath("") returns "."; we don't want that.
    if clean == ".":
        clean = ""
    return clean


def _safe_join(base: str, *paths: str) -> str:
    """Join path components, ensuring the result stays inside *base*.

    Raises ``SuspiciousFileOperation`` when the resulting path escapes
    the base directory (e.g. via ``../`` traversal).

    Args:
        base: The base path (typically the storage location/base_path).
        paths: One or more path segments to join.

    Returns:
        The joined, normalized path.

    Raises:
        SuspiciousFileOperation: If the final path is outside *base*.
    """
    base = base.rstrip("/")
    final = base + "/"
    for path in paths:
        final = posixpath.normpath(posixpath.join(final, path))
        if path.endswith("/") or final + "/" == base + "/":
            final += "/"
    if final == base:
        final += "/"

    if not final.startswith(base) or (
        len(final) > len(base) and final[len(base)] != "/"
    ):
        raise SuspiciousFileOperation(
            f"The joined path is located outside of the base path: {base!r}"
        )
    return final


class _BaseStowryStorage(Storage):
    """Base class for Stowry Django storage backends.

    Inherits from ``django.core.files.storage.Storage`` and implements the
    ``get_default_settings()`` pattern from ``django-storages``.  Subclasses
    must override ``get_default_settings`` and ``_get_url``.
    """

    # 10 MB default: files smaller than this stay in RAM; larger ones
    # are transparently spilled to a temporary file on disk.
    DEFAULT_MAX_MEMORY_SIZE: int = 10 * 1024 * 1024

    endpoint: str
    base_path: str
    max_memory_size: int

    def __init__(self, **kw: Any) -> None:
        default_settings = self.get_default_settings()

        # Apply defaults (only when the attribute is not already set, e.g.
        # via a class-level override).
        for name, value in default_settings.items():
            if not hasattr(self, name):
                setattr(self, name, value)

        # Apply caller-provided overrides, rejecting unknown keys.
        for name, value in kw.items():
            if name not in default_settings:
                raise ImproperlyConfigured(
                    f"Invalid setting {name!r} for {self.__class__.__name__}"
                )
            setattr(self, name, value)

    # -- abstract hooks --------------------------------------------------

    def get_default_settings(self) -> dict[str, Any]:
        """Return a mapping of setting names to their default values.

        Returns:
            A dict of ``{attribute_name: default_value}``.
        """
        return {}

    def _get_url(self, method: str, name: str) -> str:
        """Return the URL for the given HTTP method and file name.

        Args:
            method: HTTP method (``GET``, ``PUT``, or ``DELETE``).
            name: The file name or relative path.

        Returns:
            A URL string.
        """
        raise NotImplementedError

    # -- path helpers ----------------------------------------------------

    def _get_path(self, name: str) -> str:
        """Build the full object path from ``base_path`` and *name*.

        Uses ``_safe_join`` to prevent directory traversal attacks.

        Args:
            name: The file name or relative path.

        Returns:
            An absolute path starting with ``/``.

        Raises:
            SuspiciousFileOperation: If the resulting path escapes
                ``base_path``.
        """
        cleaned = _clean_name(name)
        return _safe_join(self.base_path, cleaned)

    # -- Storage API -----------------------------------------------------

    def _open(self, name: str, mode: str = "rb") -> File:
        url = self._get_url("GET", name)
        tmp = tempfile.SpooledTemporaryFile(
            max_size=self.max_memory_size,
            suffix=".stowry",
        )
        try:
            with urlopen(url) as response:  # noqa: S310
                shutil.copyfileobj(response, tmp)
        except (HTTPError, URLError) as exc:
            tmp.close()
            raise FileNotFoundError(f"File not found: {name}") from exc
        tmp.seek(0)
        return File(tmp, name=name)

    def url(self, name: str | None) -> str:
        """Return a download URL for the file.

        Args:
            name: The file name or relative path.

        Returns:
            A URL string for downloading the file.

        Raises:
            ValueError: If *name* is ``None``.
        """
        if name is None:
            raise ValueError("name must not be None")
        return self._get_url("GET", name)

    def upload_url(self, name: str) -> str:
        """Return an upload URL for the file.

        Clients should ``PUT`` file data directly to this URL.

        Args:
            name: The file name or relative path.

        Returns:
            A URL string for uploading the file.
        """
        return self._get_url("PUT", name)

    def delete_url(self, name: str) -> str:
        """Return a delete URL for the file.

        Clients should send a ``DELETE`` request to this URL.

        Args:
            name: The file name or relative path.

        Returns:
            A URL string for deleting the file.
        """
        return self._get_url("DELETE", name)

    def _save(self, name: str, content: File) -> str:
        raise NotImplementedError("Use upload_url() to get a URL for direct upload")

    def delete(self, name: str) -> None:
        """Not supported. Use ``delete_url()`` to get a URL for direct deletion.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError("Use delete_url() to get a URL for direct deletion")

    def exists(self, name: str) -> bool:
        """Not supported. Stowry does not expose a file existence check.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError("Stowry storage does not support exists()")

    def size(self, name: str) -> int:
        """Return the file size in bytes.

        Args:
            name: The file name or relative path.

        Raises:
            NotImplementedError: Always, as Stowry does not expose file size.
        """
        raise NotImplementedError("Stowry storage does not support size()")

    def listdir(self, path: str) -> tuple[list[str], list[str]]:
        """List contents of a directory.

        Args:
            path: The directory path.

        Raises:
            NotImplementedError: Always, as Stowry does not expose directory
            listing.
        """
        raise NotImplementedError("Stowry storage does not support listdir()")

    def path(self, name: str) -> str:
        """Return the local filesystem path.

        Args:
            name: The file name.

        Raises:
            NotImplementedError: Always, as Stowry is a remote storage backend.
        """
        raise NotImplementedError("Stowry storage does not support path()")

    def generate_filename(self, filename: str | os.PathLike[str]) -> str:
        """Return the filename unchanged.

        Overrides Django's default ``generate_filename`` which calls
        ``os.path.normpath`` and ``get_valid_name``.

        Args:
            filename: The original filename.

        Returns:
            The filename as a string, unchanged.
        """
        if isinstance(filename, os.PathLike):
            return os.fspath(filename)
        return filename


@deconstructible
class StowryStorage(_BaseStowryStorage):
    """Django storage backend for private Stowry buckets.

    All operations use presigned URLs generated by ``StowryClient``.
    Configured via Django settings or constructor keyword arguments.

    Args:
        endpoint: Stowry server URL. Falls back to ``STOWRY_ENDPOINT``.
        access_key: Access key ID. Falls back to ``STOWRY_ACCESS_KEY``.
        secret_key: Secret access key. Falls back to ``STOWRY_SECRET_KEY``.
        default_expires: URL validity in seconds (default: 900).
            Falls back to ``STOWRY_DEFAULT_EXPIRES``.
        base_path: Prefix prepended to all file paths (default: ``"/"``).
            Falls back to ``STOWRY_BASE_PATH``.
        max_memory_size: Maximum bytes kept in RAM before spilling to disk
            when opening files (default: 10 MB).
            Falls back to ``STOWRY_MAX_MEMORY_SIZE``.
    """

    access_key: str
    secret_key: str
    default_expires: int
    client: StowryClient

    def get_default_settings(self) -> dict[str, Any]:
        """Return default settings for private storage.

        Returns:
            A dict mapping attribute names to their default values, read
            from Django settings with sensible fallbacks.
        """
        return {
            "endpoint": _setting("STOWRY_ENDPOINT", ""),
            "access_key": _setting("STOWRY_ACCESS_KEY", ""),
            "secret_key": _setting("STOWRY_SECRET_KEY", ""),
            "default_expires": _setting("STOWRY_DEFAULT_EXPIRES", 900),
            "base_path": _setting("STOWRY_BASE_PATH", "/"),
            "max_memory_size": _setting(
                "STOWRY_MAX_MEMORY_SIZE", self.DEFAULT_MAX_MEMORY_SIZE
            ),
        }

    def __init__(self, **kw: Any) -> None:
        super().__init__(**kw)

        if not self.endpoint:
            raise ImproperlyConfigured(
                "STOWRY_ENDPOINT must be set in settings or passed as a keyword arg"
            )
        if not self.access_key:
            raise ImproperlyConfigured(
                "STOWRY_ACCESS_KEY must be set in settings or passed as a keyword arg"
            )
        if not self.secret_key:
            raise ImproperlyConfigured(
                "STOWRY_SECRET_KEY must be set in settings or passed as a keyword arg"
            )

        self.client = StowryClient(
            endpoint=self.endpoint,
            access_key=self.access_key,
            secret_key=self.secret_key,
        )

    def _get_url(self, method: str, name: str) -> str:
        path = self._get_path(name)
        methods = {
            "GET": "presign_get",
            "PUT": "presign_put",
            "DELETE": "presign_delete",
        }
        presign_fn = getattr(self.client, methods[method])
        return presign_fn(path, expires=self.default_expires)


@deconstructible
class StowryPublicStorage(_BaseStowryStorage):
    """Django storage backend for public Stowry buckets.

    Files are accessed via plain ``{endpoint}{path}`` URLs without signing.
    No access key or secret key is required.

    Args:
        endpoint: Stowry server URL. Falls back to ``STOWRY_ENDPOINT``.
        base_path: Prefix prepended to all file paths (default: ``"/"``).
            Falls back to ``STOWRY_BASE_PATH``.
        max_memory_size: Maximum bytes kept in RAM before spilling to disk
            when opening files (default: 10 MB).
            Falls back to ``STOWRY_MAX_MEMORY_SIZE``.
    """

    def get_default_settings(self) -> dict[str, Any]:
        """Return default settings for public storage.

        Returns:
            A dict mapping attribute names to their default values, read
            from Django settings with sensible fallbacks.
        """
        return {
            "endpoint": _setting("STOWRY_ENDPOINT", ""),
            "base_path": _setting("STOWRY_BASE_PATH", "/"),
            "max_memory_size": _setting(
                "STOWRY_MAX_MEMORY_SIZE", self.DEFAULT_MAX_MEMORY_SIZE
            ),
        }

    def __init__(self, **kw: Any) -> None:
        super().__init__(**kw)

        if not self.endpoint:
            raise ImproperlyConfigured(
                "STOWRY_ENDPOINT must be set in settings or passed as a keyword arg"
            )

    def _get_url(self, method: str, name: str) -> str:
        path = self._get_path(name)
        endpoint = self.endpoint.rstrip("/")
        return f"{endpoint}{path}"
