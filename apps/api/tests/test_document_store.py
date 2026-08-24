from hashlib import sha256
from io import BytesIO

import pytest
from botocore.exceptions import ClientError

from app.config import Settings
from app.document_store import LocalDocumentStore, S3DocumentStore, object_key


class FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[str, dict] = {}
        self.last_put: dict | None = None

    def head_object(self, *, Bucket: str, Key: str) -> dict:
        stored = self.objects.get(Key)
        if stored is None:
            raise ClientError(
                {
                    "Error": {"Code": "404", "Message": "Not Found"},
                    "ResponseMetadata": {"HTTPStatusCode": 404},
                },
                "HeadObject",
            )
        return {
            "ContentLength": len(stored["Body"]),
            "Metadata": stored.get("Metadata", {}),
            "ETag": '"existing-etag"',
        }

    def put_object(self, **kwargs) -> dict:
        self.last_put = kwargs
        self.objects[kwargs["Key"]] = dict(kwargs)
        return {"ETag": '"new-etag"'}

    def get_object(self, *, Bucket: str, Key: str) -> dict:
        return {"Body": BytesIO(self.objects[Key]["Body"])}


def test_object_key_is_content_addressed_and_namespaced() -> None:
    digest = sha256(b"source").hexdigest()
    assert object_key("raw", digest) == f"raw/sha256/{digest[:2]}/{digest[2:4]}/{digest}"
    with pytest.raises(ValueError, match="namespace"):
        object_key("other", digest)
    with pytest.raises(ValueError, match="SHA-256"):
        object_key("raw", "not-a-digest")


def test_local_store_is_idempotent_and_detects_corruption(tmp_path) -> None:
    data = b"same immutable source payload"
    digest = sha256(data).hexdigest()
    store = LocalDocumentStore(tmp_path)

    first = store.put(
        namespace="raw",
        digest=digest,
        data=data,
        content_type="text/html",
    )
    second = store.put(
        namespace="raw",
        digest=digest,
        data=data,
        content_type="text/html",
    )

    assert first.created is True
    assert second.created is False
    assert first.key == second.key
    assert store.get(first.key) == data

    (tmp_path / first.key).write_bytes(b"x" * len(data))
    with pytest.raises(RuntimeError, match="corrupted"):
        store.put(
            namespace="raw",
            digest=digest,
            data=data,
            content_type="text/html",
        )


def test_store_rejects_digest_payload_mismatch(tmp_path) -> None:
    store = LocalDocumentStore(tmp_path)
    with pytest.raises(ValueError, match="does not match"):
        store.put(
            namespace="text",
            digest=sha256(b"expected").hexdigest(),
            data=b"different",
            content_type="text/plain",
        )


def test_s3_store_writes_hash_metadata_and_kms_encryption() -> None:
    client = FakeS3Client()
    settings = Settings(
        _env_file=None,
        document_store_backend="s3",
        document_store_s3_bucket="zhituo-documents",
        document_store_s3_sse="aws:kms",
        document_store_s3_kms_key_id="alias/zhituo-documents",
    )
    store = S3DocumentStore(settings, client=client)
    data = b"archived source"
    digest = sha256(data).hexdigest()

    first = store.put(
        namespace="raw",
        digest=digest,
        data=data,
        content_type="application/pdf",
    )
    second = store.put(
        namespace="raw",
        digest=digest,
        data=data,
        content_type="application/pdf",
    )

    assert first.created is True
    assert second.created is False
    assert client.last_put is not None
    assert client.last_put["Metadata"] == {"sha256": digest}
    assert client.last_put["ServerSideEncryption"] == "aws:kms"
    assert client.last_put["SSEKMSKeyId"] == "alias/zhituo-documents"
    assert store.get(first.key) == data


def test_s3_store_rejects_existing_object_with_invalid_hash_metadata() -> None:
    client = FakeS3Client()
    settings = Settings(
        _env_file=None,
        document_store_backend="s3",
        document_store_s3_bucket="zhituo-documents",
    )
    store = S3DocumentStore(settings, client=client)
    data = b"immutable source"
    digest = sha256(data).hexdigest()
    stored = store.put(
        namespace="raw",
        digest=digest,
        data=data,
        content_type="text/html",
    )
    client.objects[stored.key]["Metadata"] = {"sha256": "0" * 64}

    with pytest.raises(RuntimeError, match="SHA-256 metadata"):
        store.put(
            namespace="raw",
            digest=digest,
            data=data,
            content_type="text/html",
        )
