# stowrypy

[![PyPI version][pypi-badge]][pypi-url]
[![Python versions][python-badge]][pypi-url]
[![CI][ci-badge]][ci-url]
[![codecov][codecov-badge]][codecov-url]
[![License][license-badge]][license-url]

[pypi-badge]: https://img.shields.io/pypi/v/stowrypy
[python-badge]: https://img.shields.io/pypi/pyversions/stowrypy
[ci-badge]: https://github.com/sagarc03/stowrypy/actions/workflows/ci.yml/badge.svg
[ci-url]: https://github.com/sagarc03/stowrypy/actions/workflows/ci.yml
[codecov-badge]: https://codecov.io/gh/sagarc03/stowrypy/graph/badge.svg
[codecov-url]: https://codecov.io/gh/sagarc03/stowrypy
[license-badge]: https://img.shields.io/pypi/l/stowrypy
[pypi-url]: https://pypi.org/project/stowrypy/
[license-url]: https://github.com/sagarc03/stowrypy/blob/main/LICENSE

A Python SDK for generating [Stowry](https://github.com/sagarc03/stowry)
presigned URLs.

## Installation

```bash
pip install stowrypy
```

## Quick Start

```python
from stowrypy import StowryClient

client = StowryClient(
    endpoint="http://localhost:5708",
    access_key="your-access-key",
    secret_key="your-secret-key",
)

# Generate a presigned URL for downloading a file
get_url = client.presign_get("/files/document.pdf")

# Generate a presigned URL for uploading a file
put_url = client.presign_put("/files/upload.txt")

# Generate a presigned URL for deleting a file
delete_url = client.presign_delete("/files/old.txt")
```

## Usage with HTTP Clients

```python
import requests
from stowrypy import StowryClient

client = StowryClient(
    endpoint="http://localhost:5708",
    access_key="your-access-key",
    secret_key="your-secret-key",
)

# Download a file
get_url = client.presign_get("/files/document.pdf")
response = requests.get(get_url)
content = response.content

# Upload a file
put_url = client.presign_put("/files/upload.txt")
requests.put(put_url, data=b"Hello, World!")

# Delete a file
delete_url = client.presign_delete("/files/old.txt")
requests.delete(delete_url)
```

## API Reference

### StowryClient

```python
StowryClient(endpoint: str, access_key: str, secret_key: str)
```

Creates a new Stowry client.

| Parameter    | Type  | Description                                        |
| ------------ | ----- | -------------------------------------------------- |
| `endpoint`   | `str` | Stowry server URL (e.g., `http://localhost:5708`)  |
| `access_key` | `str` | Access key ID                                      |
| `secret_key` | `str` | Secret access key                                  |

### Methods

#### presign_get

```python
presign_get(path: str, expires: int = 900) -> str
```

Generates a presigned URL for GET requests.

| Parameter | Type  | Default | Description                          |
| --------- | ----- | ------- | ------------------------------------ |
| `path`    | `str` | -       | Object path (must start with `/`)    |
| `expires` | `int` | `900`   | URL validity in seconds (1-604800)   |

#### presign_put

```python
presign_put(path: str, expires: int = 900) -> str
```

Generates a presigned URL for PUT requests.

| Parameter | Type  | Default | Description                          |
| --------- | ----- | ------- | ------------------------------------ |
| `path`    | `str` | -       | Object path (must start with `/`)    |
| `expires` | `int` | `900`   | URL validity in seconds (1-604800)   |

#### presign_delete

```python
presign_delete(path: str, expires: int = 900) -> str
```

Generates a presigned URL for DELETE requests.

| Parameter | Type  | Default | Description                          |
| --------- | ----- | ------- | ------------------------------------ |
| `path`    | `str` | -       | Object path (must start with `/`)    |
| `expires` | `int` | `900`   | URL validity in seconds (1-604800)   |

#### generate_presigned_url

```python
generate_presigned_url(operation: str, path: str, expires: int = 900) -> str
```

S3-compatible interface for generating presigned URLs.

| Parameter   | Type  | Default | Description                          |
| ----------- | ----- | ------- | ------------------------------------ |
| `operation` | `str` | -       | `get_object`, `put_object`, or `delete_object` |
| `path`      | `str` | -       | Object path (must start with `/`)    |
| `expires`   | `int` | `900`   | URL validity in seconds (1-604800)   |

## URL Expiration

- Default: 900 seconds (15 minutes)
- Minimum: 1 second
- Maximum: 604800 seconds (7 days)

## Signing Scheme

This SDK implements Stowry's native signing scheme. URLs are signed using
HMAC-SHA256 with the following query parameters:

| Parameter             | Description                      |
| --------------------- | -------------------------------- |
| `X-Stowry-Credential` | Access key ID                    |
| `X-Stowry-Date`       | Unix timestamp (seconds)         |
| `X-Stowry-Expires`    | Validity in seconds              |
| `X-Stowry-Signature`  | Hex-encoded HMAC-SHA256 signature |

For AWS Signature V4 compatibility, use
[boto3](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html).
The Stowry server supports both signing schemes.

## License

MIT
