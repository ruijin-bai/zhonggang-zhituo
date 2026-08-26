# Staging Image Contract

Persistent Staging must exercise the same production API/Web images that would be promoted further. It must not depend on repository-only files being mounted into containers.

## API image self-containment

The API image must contain every deterministic asset required by its supported operational commands. In particular, `zhituo-api seed` must work from the built image after database migration without access to the repository checkout.

The canonical demo fixture remains under `data/demo/opportunities.json` for repository-level inspection. A packaged copy is included under `app/demo_data/` so the Python distribution and production image carry the seed payload. Unit tests assert both copies remain semantically identical, while the image build verifies the runtime seed path exists.

This contract exists because the first full Staging smoke exposed a real packaging defect: source-based CI could seed successfully while the production image could not locate the fixture.

## Validation

A Staging change is not complete unless CI proves all of the following with built images:

1. database migration succeeds;
2. deterministic seed succeeds from the API image;
3. API, Worker, Beat and Web start;
4. PostgreSQL, Redis, MinIO and Mailpit are reachable through the intended topology;
5. Web → BFF → API → PostgreSQL smoke succeeds;
6. SMTP probe is accepted by Mailpit and observable through its API.
