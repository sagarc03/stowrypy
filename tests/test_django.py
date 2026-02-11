import pathlib
from io import BytesIO
from unittest.mock import MagicMock, patch

import django
from django.conf import settings

if not settings.configured:
    settings.configure(
        STOWRY_ENDPOINT="http://localhost:5708",
        STOWRY_ACCESS_KEY="FE373CEF5632FDED3081",
        STOWRY_SECRET_KEY="9218d0ddfdb1779169f4b6b3b36df321099e98e9",
    )
    django.setup()

from urllib.error import HTTPError

import pytest
from django.core.exceptions import ImproperlyConfigured, SuspiciousFileOperation
from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from django.test import override_settings

from stowrypy.django import (
    StowryPublicStorage,
    StowryStorage,
    _clean_name,
    _safe_join,
    _setting,
)


# --- Utility function tests ---


class TestSetting:
    def test_reads_from_django_settings(self) -> None:
        assert _setting("STOWRY_ENDPOINT") == "http://localhost:5708"

    @override_settings(STOWRY_DEFAULT_EXPIRES=3600)
    def test_reads_overridden_setting(self) -> None:
        assert _setting("STOWRY_DEFAULT_EXPIRES") == 3600

    def test_falls_back_to_default(self) -> None:
        assert _setting("STOWRY_DEFAULT_EXPIRES", 900) == 900

    def test_returns_none_for_unknown_key(self) -> None:
        assert _setting("STOWRY_NONEXISTENT") is None

    def test_returns_custom_default(self) -> None:
        assert _setting("STOWRY_NONEXISTENT", "fallback") == "fallback"


class TestCleanName:
    def test_simple_name(self) -> None:
        assert _clean_name("photos/cat.jpg") == "photos/cat.jpg"

    def test_normalizes_dot_segments(self) -> None:
        assert _clean_name("photos/../secret.txt") == "secret.txt"

    def test_preserves_trailing_slash(self) -> None:
        assert _clean_name("photos/").endswith("/")

    def test_pathlib_purepath(self) -> None:
        assert _clean_name(pathlib.PurePosixPath("photos/cat.jpg")) == "photos/cat.jpg"

    def test_empty_string(self) -> None:
        assert _clean_name("") == ""

    def test_dot_returns_empty(self) -> None:
        assert _clean_name(".") == ""

    def test_backslash_normalization(self) -> None:
        assert _clean_name("photos\\cat.jpg") == "photos/cat.jpg"


class TestSafeJoin:
    def test_simple_join(self) -> None:
        assert _safe_join("/", "photos/cat.jpg") == "/photos/cat.jpg"

    def test_join_with_base_path(self) -> None:
        assert _safe_join("/media", "photos/cat.jpg") == "/media/photos/cat.jpg"

    def test_base_path_trailing_slash(self) -> None:
        assert _safe_join("/media/", "photos/cat.jpg") == "/media/photos/cat.jpg"

    def test_traversal_raises(self) -> None:
        with pytest.raises(SuspiciousFileOperation):
            _safe_join("/media", "../../etc/passwd")

    def test_traversal_within_base_is_ok(self) -> None:
        result = _safe_join("/media", "photos/../docs/file.txt")
        assert result == "/media/docs/file.txt"

    def test_trailing_slash_preserved(self) -> None:
        result = _safe_join("/media", "photos/")
        assert result.endswith("/")


# --- Fixtures ---


@pytest.fixture
def storage() -> StowryStorage:
    return StowryStorage(
        endpoint="http://localhost:5708",
        access_key="FE373CEF5632FDED3081",
        secret_key="9218d0ddfdb1779169f4b6b3b36df321099e98e9",
    )


@pytest.fixture
def public_storage() -> StowryPublicStorage:
    return StowryPublicStorage(endpoint="http://localhost:5708")


# --- StowryStorage tests ---


class TestStowryStorageInit:
    def test_constructor_with_explicit_args(self) -> None:
        s = StowryStorage(
            endpoint="http://example.com",
            access_key="key",
            secret_key="secret",
        )
        assert s.endpoint == "http://example.com"
        assert s.access_key == "key"
        assert s.secret_key == "secret"
        assert s.default_expires == 900
        assert s.base_path == "/"

    def test_constructor_with_custom_options(self) -> None:
        s = StowryStorage(
            endpoint="http://example.com",
            access_key="key",
            secret_key="secret",
            default_expires=3600,
            base_path="/media",
        )
        assert s.default_expires == 3600
        assert s.base_path == "/media"

    def test_falls_back_to_django_settings(self) -> None:
        s = StowryStorage()
        assert s.endpoint == "http://localhost:5708"
        assert s.access_key == "FE373CEF5632FDED3081"
        assert s.secret_key == "9218d0ddfdb1779169f4b6b3b36df321099e98e9"

    @override_settings(STOWRY_ENDPOINT="")
    def test_missing_endpoint_raises(self) -> None:
        with pytest.raises(ImproperlyConfigured, match="STOWRY_ENDPOINT"):
            StowryStorage(access_key="key", secret_key="secret")

    @override_settings(STOWRY_ACCESS_KEY="")
    def test_missing_access_key_raises(self) -> None:
        with pytest.raises(ImproperlyConfigured, match="STOWRY_ACCESS_KEY"):
            StowryStorage(endpoint="http://example.com", secret_key="secret")

    @override_settings(STOWRY_SECRET_KEY="")
    def test_missing_secret_key_raises(self) -> None:
        with pytest.raises(ImproperlyConfigured, match="STOWRY_SECRET_KEY"):
            StowryStorage(endpoint="http://example.com", access_key="key")

    def test_invalid_kwarg_raises(self) -> None:
        with pytest.raises(ImproperlyConfigured, match="Invalid setting"):
            StowryStorage(
                endpoint="http://example.com",
                access_key="key",
                secret_key="secret",
                unknown_option="bad",
            )

    def test_inherits_from_storage(self) -> None:
        s = StowryStorage(
            endpoint="http://example.com",
            access_key="key",
            secret_key="secret",
        )
        assert isinstance(s, Storage)


class TestStowryStorageDefaultSettings:
    def test_get_default_settings_keys(self) -> None:
        s = StowryStorage(
            endpoint="http://example.com",
            access_key="key",
            secret_key="secret",
        )
        defaults = s.get_default_settings()
        expected_keys = {
            "endpoint",
            "access_key",
            "secret_key",
            "default_expires",
            "base_path",
            "max_memory_size",
        }
        assert set(defaults.keys()) == expected_keys

    def test_default_expires_value(self) -> None:
        s = StowryStorage(
            endpoint="http://example.com",
            access_key="key",
            secret_key="secret",
        )
        defaults = s.get_default_settings()
        assert defaults["default_expires"] == 900

    def test_default_base_path_value(self) -> None:
        s = StowryStorage(
            endpoint="http://example.com",
            access_key="key",
            secret_key="secret",
        )
        defaults = s.get_default_settings()
        assert defaults["base_path"] == "/"

    def test_default_max_memory_size(self) -> None:
        s = StowryStorage(
            endpoint="http://example.com",
            access_key="key",
            secret_key="secret",
        )
        assert s.max_memory_size == 10 * 1024 * 1024

    def test_custom_max_memory_size(self) -> None:
        s = StowryStorage(
            endpoint="http://example.com",
            access_key="key",
            secret_key="secret",
            max_memory_size=1024,
        )
        assert s.max_memory_size == 1024


class TestStowryStorageGetPath:
    def test_default_base_path(self, storage: StowryStorage) -> None:
        assert storage._get_path("photos/cat.jpg") == "/photos/cat.jpg"

    def test_custom_base_path(self) -> None:
        s = StowryStorage(
            endpoint="http://example.com",
            access_key="key",
            secret_key="secret",
            base_path="/media",
        )
        assert s._get_path("photos/cat.jpg") == "/media/photos/cat.jpg"

    def test_base_path_trailing_slash(self) -> None:
        s = StowryStorage(
            endpoint="http://example.com",
            access_key="key",
            secret_key="secret",
            base_path="/media/",
        )
        assert s._get_path("photos/cat.jpg") == "/media/photos/cat.jpg"

    def test_name_with_leading_slash(self, storage: StowryStorage) -> None:
        assert storage._get_path("/photos/cat.jpg") == "/photos/cat.jpg"

    def test_traversal_raises_with_custom_base(self) -> None:
        s = StowryStorage(
            endpoint="http://example.com",
            access_key="key",
            secret_key="secret",
            base_path="/media",
        )
        with pytest.raises(SuspiciousFileOperation):
            s._get_path("../../etc/passwd")

    def test_traversal_within_base_path(self) -> None:
        s = StowryStorage(
            endpoint="http://example.com",
            access_key="key",
            secret_key="secret",
            base_path="/media",
        )
        assert s._get_path("photos/../docs/file.txt") == "/media/docs/file.txt"


class TestStowryStorageUrl:
    def test_returns_presigned_get_url(self, storage: StowryStorage) -> None:
        url = storage.url("photos/cat.jpg")
        assert url.startswith("http://localhost:5708/photos/cat.jpg?")
        assert "X-Stowry-Credential=FE373CEF5632FDED3081" in url
        assert "X-Stowry-Signature=" in url

    def test_custom_base_path_in_url(self) -> None:
        s = StowryStorage(
            endpoint="http://example.com",
            access_key="key",
            secret_key="secret",
            base_path="/media",
        )
        url = s.url("file.txt")
        assert "/media/file.txt?" in url

    def test_url_none_raises(self, storage: StowryStorage) -> None:
        with pytest.raises(ValueError, match="name must not be None"):
            storage.url(None)


class TestStowryStorageUploadUrl:
    def test_returns_presigned_put_url(self, storage: StowryStorage) -> None:
        url = storage.upload_url("photos/cat.jpg")
        assert url.startswith("http://localhost:5708/photos/cat.jpg?")
        assert "X-Stowry-Credential=FE373CEF5632FDED3081" in url
        assert "X-Stowry-Signature=" in url

    def test_custom_base_path(self) -> None:
        s = StowryStorage(
            endpoint="http://example.com",
            access_key="key",
            secret_key="secret",
            base_path="/uploads",
        )
        url = s.upload_url("file.txt")
        assert "/uploads/file.txt?" in url


class TestStowryStorageDeleteUrl:
    def test_returns_presigned_delete_url(self, storage: StowryStorage) -> None:
        url = storage.delete_url("photos/cat.jpg")
        assert url.startswith("http://localhost:5708/photos/cat.jpg?")
        assert "X-Stowry-Credential=FE373CEF5632FDED3081" in url
        assert "X-Stowry-Signature=" in url

    def test_custom_base_path(self) -> None:
        s = StowryStorage(
            endpoint="http://example.com",
            access_key="key",
            secret_key="secret",
            base_path="/data",
        )
        url = s.delete_url("old.txt")
        assert "/data/old.txt?" in url


class TestStowryStorageOpen:
    @patch("stowrypy.django.urlopen")
    def test_returns_file_with_content(
        self, mock_urlopen: MagicMock, storage: StowryStorage
    ) -> None:
        body = BytesIO(b"file content")
        mock_urlopen.return_value.__enter__ = MagicMock(return_value=body)
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        result = storage.open("test.txt")
        assert result.read() == b"file content"

    @patch("stowrypy.django.urlopen")
    def test_raises_file_not_found_on_http_error(
        self, mock_urlopen: MagicMock, storage: StowryStorage
    ) -> None:
        mock_urlopen.side_effect = HTTPError(
            url="http://example.com",
            code=404,
            msg="Not Found",
            hdrs=MagicMock(),
            fp=None,
        )
        with pytest.raises(FileNotFoundError, match="File not found: test.txt"):
            storage.open("test.txt")


class TestStowryStorageNotImplemented:
    def test_save_raises(self, storage: StowryStorage) -> None:
        with pytest.raises(NotImplementedError):
            storage.save("file.txt", ContentFile(b"data"))

    def test_delete_raises(self, storage: StowryStorage) -> None:
        with pytest.raises(NotImplementedError, match="delete_url"):
            storage.delete("file.txt")

    def test_exists_raises(self, storage: StowryStorage) -> None:
        with pytest.raises(NotImplementedError, match="exists"):
            storage.exists("file.txt")

    def test_size_raises(self, storage: StowryStorage) -> None:
        with pytest.raises(NotImplementedError, match="size"):
            storage.size("file.txt")

    def test_listdir_raises(self, storage: StowryStorage) -> None:
        with pytest.raises(NotImplementedError, match="listdir"):
            storage.listdir("/")

    def test_path_raises(self, storage: StowryStorage) -> None:
        with pytest.raises(NotImplementedError, match="path"):
            storage.path("file.txt")


class TestStowryStorageDeconstructible:
    def test_can_deconstruct(self, storage: StowryStorage) -> None:
        path, args, kwargs = storage.deconstruct()
        assert path == "stowrypy.django.StowryStorage"
        assert args == ()
        assert "endpoint" in kwargs


class TestStowryStorageGenerateFilename:
    def test_returns_filename_unchanged(self, storage: StowryStorage) -> None:
        assert storage.generate_filename("photo.jpg") == "photo.jpg"

    def test_accepts_pathlike(self, storage: StowryStorage) -> None:
        result = storage.generate_filename(pathlib.PurePosixPath("photo.jpg"))
        assert result == "photo.jpg"


# --- StowryPublicStorage tests ---


class TestPublicStorageInit:
    def test_constructor_with_explicit_args(self) -> None:
        s = StowryPublicStorage(endpoint="http://example.com")
        assert s.endpoint == "http://example.com"
        assert s.base_path == "/"

    def test_constructor_with_custom_base_path(self) -> None:
        s = StowryPublicStorage(endpoint="http://example.com", base_path="/public")
        assert s.base_path == "/public"

    def test_falls_back_to_django_settings(self) -> None:
        s = StowryPublicStorage()
        assert s.endpoint == "http://localhost:5708"

    @override_settings(STOWRY_ENDPOINT="")
    def test_missing_endpoint_raises(self) -> None:
        with pytest.raises(ImproperlyConfigured, match="STOWRY_ENDPOINT"):
            StowryPublicStorage()

    def test_no_access_key_or_secret_key_required(self) -> None:
        s = StowryPublicStorage(endpoint="http://example.com")
        assert not hasattr(s, "access_key")
        assert not hasattr(s, "secret_key")
        assert not hasattr(s, "client")

    def test_invalid_kwarg_raises(self) -> None:
        with pytest.raises(ImproperlyConfigured, match="Invalid setting"):
            StowryPublicStorage(endpoint="http://example.com", bad_option="nope")

    def test_inherits_from_storage(self) -> None:
        s = StowryPublicStorage(endpoint="http://example.com")
        assert isinstance(s, Storage)


class TestPublicStorageDefaultSettings:
    def test_get_default_settings_keys(self) -> None:
        s = StowryPublicStorage(endpoint="http://example.com")
        defaults = s.get_default_settings()
        expected_keys = {"endpoint", "base_path", "max_memory_size"}
        assert set(defaults.keys()) == expected_keys

    def test_default_max_memory_size(self) -> None:
        s = StowryPublicStorage(endpoint="http://example.com")
        assert s.max_memory_size == 10 * 1024 * 1024

    def test_custom_max_memory_size(self) -> None:
        s = StowryPublicStorage(endpoint="http://example.com", max_memory_size=2048)
        assert s.max_memory_size == 2048


class TestPublicStorageUrl:
    def test_returns_plain_url(self, public_storage: StowryPublicStorage) -> None:
        url = public_storage.url("photos/cat.jpg")
        assert url == "http://localhost:5708/photos/cat.jpg"

    def test_no_query_string(self, public_storage: StowryPublicStorage) -> None:
        url = public_storage.url("file.txt")
        assert "?" not in url

    def test_custom_base_path(self) -> None:
        s = StowryPublicStorage(endpoint="http://example.com", base_path="/public")
        url = s.url("doc.pdf")
        assert url == "http://example.com/public/doc.pdf"

    def test_trailing_slash_on_endpoint(self) -> None:
        s = StowryPublicStorage(endpoint="http://example.com/")
        url = s.url("file.txt")
        assert url == "http://example.com/file.txt"

    def test_url_none_raises(self, public_storage: StowryPublicStorage) -> None:
        with pytest.raises(ValueError, match="name must not be None"):
            public_storage.url(None)


class TestPublicStorageUploadUrl:
    def test_returns_plain_url(self, public_storage: StowryPublicStorage) -> None:
        url = public_storage.upload_url("photos/cat.jpg")
        assert url == "http://localhost:5708/photos/cat.jpg"

    def test_no_query_string(self, public_storage: StowryPublicStorage) -> None:
        url = public_storage.upload_url("file.txt")
        assert "?" not in url

    def test_custom_base_path(self) -> None:
        s = StowryPublicStorage(endpoint="http://example.com", base_path="/uploads")
        url = s.upload_url("file.txt")
        assert url == "http://example.com/uploads/file.txt"


class TestPublicStorageDeleteUrl:
    def test_returns_plain_url(self, public_storage: StowryPublicStorage) -> None:
        url = public_storage.delete_url("old.txt")
        assert url == "http://localhost:5708/old.txt"

    def test_no_query_string(self, public_storage: StowryPublicStorage) -> None:
        url = public_storage.delete_url("file.txt")
        assert "?" not in url


class TestPublicStorageOpen:
    @patch("stowrypy.django.urlopen")
    def test_returns_file_with_content(
        self, mock_urlopen: MagicMock, public_storage: StowryPublicStorage
    ) -> None:
        body = BytesIO(b"public data")
        mock_urlopen.return_value.__enter__ = MagicMock(return_value=body)
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        result = public_storage.open("test.txt")
        assert result.read() == b"public data"
        mock_urlopen.assert_called_once_with("http://localhost:5708/test.txt")

    @patch("stowrypy.django.urlopen")
    def test_raises_file_not_found_on_http_error(
        self, mock_urlopen: MagicMock, public_storage: StowryPublicStorage
    ) -> None:
        mock_urlopen.side_effect = HTTPError(
            url="http://example.com",
            code=404,
            msg="Not Found",
            hdrs=MagicMock(),
            fp=None,
        )
        with pytest.raises(FileNotFoundError, match="File not found: test.txt"):
            public_storage.open("test.txt")


class TestPublicStorageNotImplemented:
    def test_save_raises(self, public_storage: StowryPublicStorage) -> None:
        with pytest.raises(NotImplementedError):
            public_storage.save("file.txt", ContentFile(b"data"))

    def test_delete_raises(self, public_storage: StowryPublicStorage) -> None:
        with pytest.raises(NotImplementedError, match="delete_url"):
            public_storage.delete("file.txt")

    def test_exists_raises(self, public_storage: StowryPublicStorage) -> None:
        with pytest.raises(NotImplementedError, match="exists"):
            public_storage.exists("file.txt")

    def test_size_raises(self, public_storage: StowryPublicStorage) -> None:
        with pytest.raises(NotImplementedError, match="size"):
            public_storage.size("file.txt")

    def test_listdir_raises(self, public_storage: StowryPublicStorage) -> None:
        with pytest.raises(NotImplementedError, match="listdir"):
            public_storage.listdir("/")

    def test_path_raises(self, public_storage: StowryPublicStorage) -> None:
        with pytest.raises(NotImplementedError, match="path"):
            public_storage.path("file.txt")


class TestPublicStorageGetPath:
    def test_traversal_raises_with_custom_base(self) -> None:
        s = StowryPublicStorage(endpoint="http://example.com", base_path="/public")
        with pytest.raises(SuspiciousFileOperation):
            s._get_path("../../etc/passwd")


class TestPublicStorageDeconstructible:
    def test_can_deconstruct(self, public_storage: StowryPublicStorage) -> None:
        path, args, kwargs = public_storage.deconstruct()
        assert path == "stowrypy.django.StowryPublicStorage"
        assert args == ()
        assert "endpoint" in kwargs


class TestPublicStorageGenerateFilename:
    def test_returns_filename_unchanged(
        self, public_storage: StowryPublicStorage
    ) -> None:
        assert public_storage.generate_filename("photo.jpg") == "photo.jpg"

    def test_accepts_pathlike(self, public_storage: StowryPublicStorage) -> None:
        result = public_storage.generate_filename(pathlib.PurePosixPath("photo.jpg"))
        assert result == "photo.jpg"
