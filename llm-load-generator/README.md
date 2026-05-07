# LLM Load Generator

A load generator for vLLM inference endpoints hosted on OpenShift. It sends a sustained stream
of LLM chat completion requests instrumented with
[OpenLLMetry](https://github.com/traceloop/openllmetry) to export traces, metrics, and logs to
Dynatrace.

## Overview

1. Builds a prompt pool by shuffling the cross-product of:
   - `SYSTEM_PROMPTS` (10)
   - `TOPICS` (~100)
   - `ACTIONS` (10)
2. Iterates through the shuffled pool, sending one request at a time with a random 15-45 second
   delay.
3. Prints per-request progress including index, tokens, duration, running totals, and requests
   per hour.

The full 2000-prompt run typically takes around 3-4 days at the configured delay interval.

## Prerequisites

- Python 3.x
- `pip install -r requirements.txt`
- A running Kubernetes cluster with `kubectl` configured
- Network reachability to the vLLM endpoint, either from inside the cluster or via an exposed
  OpenShift route or port-forward
- A vLLM endpoint serving `Qwen/Qwen3-4B`
- A Dynatrace environment with an API token scoped for:
  - `metrics.ingest`
  - `logs.ingest`
  - `openTelemetryTrace.ingest`
- SSL certificate verification is intentionally disabled to allow self-signed certs on OpenShift
  routes

## Environment Variables

| Env Var | Required | Default | Description |
|---------|----------|---------|-------------|
| `OTEL_ENDPOINT` | No | — | OTLP endpoint, for example `https://<ENV>.live.dynatrace.com/api/v2/otlp` |
| `DT_API_TOKEN` | No | — | Dynatrace API token with `metrics.ingest`, `logs.ingest`, and `openTelemetryTrace.ingest` scopes |
| `LLM_URL` | Yes | — | vLLM base URL, for example `https://<HOSTNAME>/v1` |
| `LLM_MODEL` | Yes | — | vLLM model name, for example `Qwen/Qwen3-4B` |
| `APP_NAME` | No | `llm-load-generator` | Application name reported in OpenLLMetry telemetry |

If `OTEL_ENDPOINT` or `DT_API_TOKEN` is missing, the generator still runs but OpenLLMetry export
is disabled.

## Configuration

| Setting | Value |
|---------|-------|
| `max_tokens` | Randomly chosen per request from `64`, `128`, `200`, `256` |
| `temperature` | Randomly chosen per request from `uniform(0.5, 0.9)` |
| `delay` | Random sleep between requests: `uniform(15, 45)` seconds |
| `model` | Set via `LLM_MODEL` |
| `prompt pool` | Built from the full cross-product, then capped by `--num-prompts` after shuffling |

## CLI Arguments

| CLI Arg | Default | Description |
|---------|---------|-------------|
| `--num-prompts` | `1` | Number of prompts to send (max `10000`) |
| `--verbose` | `false` | Print each prompt and response |

## Run Locally

From this directory:

```bash
pip install -r requirements.txt
```

Minimal run with the required vLLM configuration:

```bash
export LLM_URL=https://my-vllm.example.com/v1
export LLM_MODEL=Qwen/Qwen3-4B

python llm-load-generator.py
```

With Dynatrace telemetry enabled:

```bash
export OTEL_ENDPOINT=https://<ENV>.live.dynatrace.com/api/v2/otlp
export DT_API_TOKEN=<your-dynatrace-api-token>
export LLM_URL=https://my-vllm.example.com/v1
export LLM_MODEL=Qwen/Qwen3-4B

python llm-load-generator.py --num-prompts 10
```

Verbose run:

```bash
python llm-load-generator.py --num-prompts 5 --verbose
```

Full prompt-pool run:

```bash
python llm-load-generator.py --num-prompts 2000
```

## Build the Container Image

The recommended Docker workflow uses the provided `Makefile` targets:

```bash
make build
```

This builds the image defined in the `Makefile`:

```text
dtdemos/llm-load-generator:v1.0.0
```

```bash
make buildx   # multi-arch build and push
make push     # push the versioned image
make login    # refresh Docker registry credentials
```

If you need to run the equivalent Docker command directly:

```bash
docker build -t dtdemos/llm-load-generator:v1.0.0 .
```

## Run in a Container

```bash
# Minimal run - 1 prompt, no telemetry export
docker run --rm \
  -e LLM_URL=https://my-vllm.example.com/v1 \
  -e LLM_MODEL=Qwen/Qwen3-4B \
  dtdemos/llm-load-generator:v1.0.0

# With Dynatrace telemetry and a custom vLLM URL
docker run --rm \
  -e OTEL_ENDPOINT=https://<ENV>.live.dynatrace.com/api/v2/otlp \
  -e DT_API_TOKEN=<your-dynatrace-api-token> \
  -e LLM_URL=https://my-vllm.example.com/v1 \
  -e LLM_MODEL=Qwen/Qwen3-4B \
  -e APP_NAME=my-llm-app \
  dtdemos/llm-load-generator:v1.0.0 --num-prompts 10 --verbose
```

## Deploy to Kubernetes

### 1. Configure the Secret

Edit [k8s/secret.yaml](k8s/secret.yaml) and fill in your values:

| Key | Description |
|-----|-------------|
| `OTEL_ENDPOINT` | OTLP endpoint (`https://<ENV>.live.dynatrace.com/api/v2/otlp`) |
| `DT_API_TOKEN` | Dynatrace API token with the required ingest scopes |
| `LLM_URL` | Base URL of your vLLM OpenAI-compatible endpoint |
| `LLM_MODEL` | Model name served by vLLM (default: `Qwen/Qwen3-4B`) |

Apply the secret:

```bash
kubectl apply -f k8s/secret.yaml
```

> **Note:** Never commit a secret.yaml with real credentials. Use `kubectl create secret` or
> a secrets manager for production.

### 2. Update the Image Reference

If you pushed to a registry, update the `image:` field in [k8s/job.yaml](k8s/job.yaml):

```yaml
image: dtdemos/llm-load-generator:v1.0.0
```

Change `imagePullPolicy` to `Always` when pulling from a remote registry.

### 3. Adjust the Prompt Count (optional)

The default job runs 2000 prompts (~3-4 days). Edit the `args` in [k8s/job.yaml](k8s/job.yaml):

```yaml
args:
  - "--num-prompts"
  - "100"   # change to your desired count
```

### 4. Submit the Job

```bash
kubectl apply -f k8s/job.yaml
```

### 5. Monitor Progress

```bash
# Watch job status
kubectl get job llm-load-generator -w

# Stream logs
kubectl logs -f job/llm-load-generator
```

### 6. Clean Up

The job deletes itself 1 hour after completion (`ttlSecondsAfterFinished: 3600`).
To delete it manually:

```bash
kubectl delete -f k8s/job.yaml
kubectl delete -f k8s/secret.yaml
```

## File Layout

```
llm-load-generator/
├── llm-load-generator.py  # Load generator source
├── requirements.txt  # Python dependencies
├── Dockerfile        # Container image definition
├── Makefile          # Docker build and push shortcuts
├── README.md         # This file
└── k8s/
    ├── secret.yaml   # Credentials (fill in before applying)
    └── job.yaml      # Kubernetes Job manifest
```
