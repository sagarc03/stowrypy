import pytest

from stowrypy import StowryClient


@pytest.fixture
def client() -> StowryClient:
    return StowryClient(
        endpoint="http://localhost:5708",
        access_key="FE373CEF5632FDED3081",
        secret_key="9218d0ddfdb1779169f4b6b3b36df321099e98e9",
    )


class TestSignature:
    def test_signature_matches_test_vector(self, client: StowryClient) -> None:
        signature = client._sign(
            method="GET",
            path="/test/hello.txt",
            timestamp=1736956800,
            expires=900,
        )
        assert (
            signature
            == "b24285352583edb3d06c531f61e38c5706d42d79e31474bf1f95667d524bae21"
        )


class TestPresignGet:
    def test_generates_valid_url(self, client: StowryClient) -> None:
        url = client._presign("GET", "/test/hello.txt", 900, timestamp=1736956800)
        assert url == (
            "http://localhost:5708/test/hello.txt?"
            "X-Stowry-Credential=FE373CEF5632FDED3081&"
            "X-Stowry-Date=1736956800&"
            "X-Stowry-Expires=900&"
            "X-Stowry-Signature=b24285352583edb3d06c531f61e38c5706d42d79e31474bf1f95667d524bae21"
        )

    def test_presign_get_uses_get_method(self, client: StowryClient) -> None:
        url = client.presign_get("/files/doc.pdf")
        assert "X-Stowry-Credential=FE373CEF5632FDED3081" in url

    def test_presign_put_uses_put_method(self, client: StowryClient) -> None:
        url = client.presign_put("/files/doc.pdf")
        assert "X-Stowry-Credential=FE373CEF5632FDED3081" in url

    def test_presign_delete_uses_delete_method(self, client: StowryClient) -> None:
        url = client.presign_delete("/files/doc.pdf")
        assert "X-Stowry-Credential=FE373CEF5632FDED3081" in url


class TestValidation:
    def test_path_must_start_with_slash(self, client: StowryClient) -> None:
        with pytest.raises(ValueError, match="Path must start with '/'"):
            client.presign_get("files/doc.pdf")

    def test_expires_minimum(self, client: StowryClient) -> None:
        with pytest.raises(ValueError, match="Expires must be between"):
            client.presign_get("/files/doc.pdf", expires=0)

    def test_expires_maximum(self, client: StowryClient) -> None:
        with pytest.raises(ValueError, match="Expires must be between"):
            client.presign_get("/files/doc.pdf", expires=604801)

    def test_expires_at_boundaries(self, client: StowryClient) -> None:
        client.presign_get("/files/doc.pdf", expires=1)
        client.presign_get("/files/doc.pdf", expires=604800)


class TestEndpointHandling:
    def test_strips_trailing_slash(self) -> None:
        client = StowryClient(
            endpoint="http://localhost:5708/",
            access_key="key",
            secret_key="secret",
        )
        assert client.endpoint == "http://localhost:5708"


class TestGeneratePresignedUrl:
    def test_get_object(self, client: StowryClient) -> None:
        url = client.generate_presigned_url("get_object", "/files/doc.pdf")
        assert "X-Stowry-Credential=FE373CEF5632FDED3081" in url

    def test_put_object(self, client: StowryClient) -> None:
        url = client.generate_presigned_url("put_object", "/files/doc.pdf")
        assert "X-Stowry-Credential=FE373CEF5632FDED3081" in url

    def test_delete_object(self, client: StowryClient) -> None:
        url = client.generate_presigned_url("delete_object", "/files/doc.pdf")
        assert "X-Stowry-Credential=FE373CEF5632FDED3081" in url
