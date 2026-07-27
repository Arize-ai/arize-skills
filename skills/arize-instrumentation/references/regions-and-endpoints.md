# Regions and endpoints

Use this when configuring or verifying where an app sends Arize traces. App trace export, `ax` CLI profiles, and Flight export use related but different settings.

## Do not assume US

On cold start, inspect the target app's own config for `ARIZE_COLLECTOR_ENDPOINT`, `OTEL_EXPORTER_OTLP_ENDPOINT`, or an in-code Arize endpoint option. If one is present, preserve it and report mismatches instead of replacing it.

If the app has no endpoint configured and the user's Arize region is unknown, ask which SaaS region they use: US, EU, or Canada. Use US only as an explicit default when no region is known and you say that is what you are doing.

## App trace export endpoints

For `arize-otel-python` and OTLP HTTP trace export:

| Cluster | Endpoint |
| --- | --- |
| US | `https://otlp.arize.com/v1` |
| US regional alias | `https://otlp.us-central-1a.arize.com/v1` |
| EU | `https://otlp.eu-west-1a.arize.com/v1` |
| Canada | `https://otlp.ca-central-1a.arize.com/v1` |

`arize-otel-python` currently has endpoint constants for US and EU. For Canada, pass the endpoint as a string.

For OTLP gRPC/base endpoint configuration, omit the `/v1` suffix:

| Cluster | Endpoint |
| --- | --- |
| US | `https://otlp.arize.com` |
| US regional alias | `https://otlp.us-central-1a.arize.com` |
| EU | `https://otlp.eu-west-1a.arize.com` |
| Canada | `https://otlp.ca-central-1a.arize.com` |

## Go

`arize-otel-go` reads `ARIZE_COLLECTOR_ENDPOINT` when `Options.Endpoint` is unset. Use `EndpointArizeEurope` for EU when appropriate; for Canada or explicit aliases, preserve or set `ARIZE_COLLECTOR_ENDPOINT` to the target OTLP endpoint.

See [go.md](go.md) for Go setup order, provider wiring, and shutdown rules.

## CLI profile region

`ax profiles create --region ...` and `ax profiles update --region ...` configure CLI/API routing for `ax` commands. They do not configure the running app's trace exporter. During verification, compare the app exporter endpoint/space/project against the active `ax` profile before declaring traces missing.

See [ax-profiles.md](ax-profiles.md) for profile setup.

## Flight endpoints

Flight is used by SDK/CLI bulk export paths, not normal app OTLP trace export.

| Cluster | Flight endpoint |
| --- | --- |
| US | `flight.arize.com:443` |
| US regional alias | `flight.us-central-1a.arize.com:443` |
| EU | `flight.eu-west-1a.arize.com:443` |
| Canada | `flight.ca-central-1a.arize.com:443` |

For SDK configuration that accepts `flight_host` plus `flight_port`, do not include `:443` in `flight_host`. Use `flight_port=443` only if explicitly overriding the default.
