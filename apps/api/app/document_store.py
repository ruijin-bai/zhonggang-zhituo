from __future__ import annotations

import re
from hashlib import sha256
from pathlib import Path
from typing import Protocol

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from pydantic import BaseModel

from .config import Settings, get_settings

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_NAMESPACES = {"raw", "text"}


class StoredObject(BaseModel):
    backend: str
    key: str
    sha256: str
    size_bytes: int
    content_type: str
    created: bool
    etag: str | None = None


class DocumentStore(Protocol):
    backend: str

    def put(
        self,
        *,
        namespace: str,
        digest: str,
        data: bytes,
        content_type: str,
    ) -> StoredObject: ...

    def get(self, key: str) -> bytes: ...


def _validate_digest(digest: str, data: bytes) -> str:
    normalized = digest.strip().lower()
    if not _SHA256_RE.fullmatch(normalized):
        raise ValueError("document object digest must be a lowercase SHA-256 hex string")
    actual = sha256(data).hexdigest()
    if actual != normalized:
        raise ValueError("document object digest does not match payload")
    return normalized


def object_key(namespace: str, digest: str) -> str:
    if namespace not in _ALLOWED_NAMESPACES:
        raise ValueError(f"unsupported document object namespace: {namespace}")
    normalized = digest.strip().lower()
    if not _SHA256_RE.fullmatch(normalized):
        raise ValueError("document object digest must be a lowercase SHA-256 hex string")
    return f"{namespace}/sha256/{normalized[:2]}/{normalized[2:4]}/{normalized}"


class LocalDocumentStore:
    backend = "local"

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()

    def _path(self, key: str) -> Path:
        candidate = (self.root / key).resolve()
        if self.root != candidate and self.root not in candidate.parents:
            raise ValueError("document object key escapes local storage root")
        return candidate

    def put(
        self,
        *,
        namespace: str,
        digest: str,
        data: bytes,
        content_type: str,
    ) -> StoredObject:
        normalized = _validate_digest(digest, data)
        key = object_key(namespace, normalized)
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        created = False
        try:
            with path.open("xb") as handle:
                handle.write(data)
            created = True
        except FileExistsError:
            existing = path.read_bytes()
            if sha256(existing).hexdigest() != normalized:
                raise RuntimeError("content-addressed local object is corrupted")
        return StoredObject(
            backend=self.backend,
            key=key,
            sha256=normalized,
            size_bytes=len(data),
            content_type=content_type,
            created=created,
        )

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()


class S3DocumentStore:
    backend = "s3"

    def __init__(self, settings: Settings, *, client=None) -> None:
        if not settings.document_store_s3_bucket:
            raise ValueError("DOCUMENT_STORE_S3_BUCKET is required for S3 document storage")
        self.bucket = settings.document_store_s3_bucket
        self.sse = settings.document_store_s3_sse
        self.kms_key_id = settings.document_store_s3_kms_key_id
        if client is not None:
            self.client = client
            return

        config = Config(
            signature_version="s3v4",
            retries={"max_attempts": 4, "mode": "standard"},
            s3={
                "addressing_style": (
                    "path" if settings.document_store_s3_force_path_style else "auto"
                )
            },
        )
        self.client = boto3.client(
            "s3",
            region_name=settings.document_store_s3_region or None,
            endpoint_url=settings.document_store_s3_endpoint_url or None,
            config=config,
        )

    def _head(self, key: str) -> dict | None:
        try:
            return self.client.head_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if code in {"404", "NoSuchKey", "NotFound"} or status == 404:
                return None
            raise

    def put(
        self,
        *,
        namespace: str,
        digest: str,
        data: bytes,
        content_type: str,
    ) -> StoredObject:
        normalized = _validate_digest(digest, data)
        key = object_key(namespace, normalized)
        head = self._head(key)
        if head is not None:
            if int(head.get("ContentLength", len(data))) != len(data):
                raise RuntimeError("content-addressed S3 object has an unexpected size")
            return StoredObject(
                backend=self.backend,
                key=key,
                sha256=normalized,
                size_bytes=len(data),
                content_type=content_type,
                created=False,
                etag=str(head.get("ETag", "")).strip('"') or None,
            )

        kwargs: dict = {
            "Bucket": self.bucket,
            "Key": key,
            "Body": data,
            "ContentType": content_type,
            "Metadata": {"sha256": normalized},
        }
        if self.sse:
            kwargs["ServerSideEncryption"] = self.sse
        if self.sse == "aws:kms":
            kwargs["SSEKMSKeyId"] = self.kms_key_id
        response = self.client.put_object(**kwargs)
        return StoredObject(
            backend=self.backend,
            key=key,
            sha256=normalized,
            size_bytes=len(data),
            content_type=content_type,
            created=True,
            etag=str(response.get("ETag", "")).strip('"') or None,
        )

    def get(self, key: str) -> bytes:
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        body = response["Body"]
        return body.read()


def build_document_store(settings: Settings | None = None) -> DocumentStore:
    resolved = settings or get_settings()
    if resolved.document_store_backend == "local":
        return LocalDocumentStore(resolved.document_store_local_path)
    if resolved.document_store_backend == "s3":
        return S3DocumentStore(resolved)
    raise ValueError(f"unsupported document store backend: {resolved.document_store_backend}")
