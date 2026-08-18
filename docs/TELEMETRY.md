# Client telemetry protocol

The client sends `POST /api/v1/telemetry` over HTTPS. The canonical signature
input is the UTF-8 sequence `timestamp + "\\n" + nonce + "\\n" + raw_body`.
The signature is lowercase HMAC-SHA256 hex.

Required headers:

- `X-Device-ID`
- `X-Timestamp` — Unix seconds
- `X-Nonce` — unique URL-safe random value, at least 16 characters
- `X-Signature`

Each device has an environment key such as
`HOSTFRONT_TELEMETRY_KEY_PHONE_1`. Nonces are unique per device and persisted in
SQLite, so replayed requests are rejected even after a server restart.

Example client command:

```bash
export HOSTFRONT_DEVICE_KEY='...'
hostfront-manager telemetry-submit \
  --endpoint https://manager.example.com \
  --device-id phone-1 \
  --path-id reality-xhttp --status up --latency-ms 54 \
  --network mobile --operator MTS --country RU
```

Secrets must be placed in Android Keystore or iOS Keychain in a native client.
The documented protocol is intentionally platform-neutral.
