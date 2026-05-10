import argparse
import os
import time
import random

import openai
from opentelemetry.context import Context
from opentelemetry import trace
from opentelemetry.trace import SpanKind
from traceloop.sdk import Traceloop

# ---------------------------------------------------------------------------
# OpenLLMetry / Dynatrace initialisation
# ---------------------------------------------------------------------------
os.environ.setdefault("OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE", "delta")

_otel_endpoint = os.environ.get("OTEL_ENDPOINT", "")
_dt_token = os.environ.get("DT_API_TOKEN", "")
_app_name = os.environ.get("APP_NAME", "llm-load-generator")

if _otel_endpoint and _dt_token:
    Traceloop.init(
        app_name=_app_name,
        api_endpoint=_otel_endpoint,
        headers={"Authorization": f"Api-Token {_dt_token}"},
        disable_batch=False,
    )
else:
    print("WARNING: OTEL_ENDPOINT or DT_API_TOKEN not set — OpenLLMetry telemetry disabled.")
    Traceloop.init(app_name=_app_name, disable_batch=True)

# ---------------------------------------------------------------------------
# vLLM OpenAI-compatible client (SSL verification disabled for OpenShift routes)
# ---------------------------------------------------------------------------
VLLM_BASE_URL = os.environ["LLM_URL"]
LLM_MODEL = os.environ["LLM_MODEL"]

client = openai.OpenAI(
    base_url=VLLM_BASE_URL,
    api_key="unused",  # vLLM does not require a real key
    timeout=120.0,
)

tracer = trace.get_tracer("llm-load-generator")

# ---------------------------------------------------------------------------
# Prompt pool
# ---------------------------------------------------------------------------
SYSTEM_PROMPTS = [
    "You are an expert Kubernetes administrator.",
    "You are a Python developer specializing in machine learning.",
    "You are a financial analyst reviewing quarterly earnings.",
    "You are a cloud architect designing multi-region deployments.",
    "You are a DevOps engineer focused on CI/CD pipelines.",
    "You are a security researcher analyzing vulnerabilities.",
    "You are a database administrator optimizing query performance.",
    "You are a technical writer creating API documentation.",
    "You are a data scientist building recommendation systems.",
    "You are a site reliability engineer managing production systems.",
]

TOPICS = [
    "pod scheduling with node affinity and taints",
    "persistent volume claims and dynamic provisioning",
    "horizontal pod autoscaling with custom metrics",
    "network policies between namespaces",
    "service mesh configuration with Istio",
    "RBAC policies and service accounts",
    "ConfigMaps and Secrets management",
    "init containers and sidecar patterns",
    "StatefulSet vs Deployment trade-offs",
    "resource quotas and limit ranges",
    "gradient descent optimization techniques",
    "batch normalization vs layer normalization",
    "attention mechanisms in transformers",
    "custom PyTorch training loops",
    "distributed training with DeepSpeed",
    "model quantization and pruning",
    "transfer learning strategies",
    "hyperparameter tuning with Optuna",
    "feature engineering for tabular data",
    "embedding models for semantic search",
    "rising interest rates and tech valuations",
    "cloud computing revenue growth trends",
    "supply chain disruption impacts on margins",
    "R&D spending correlation with innovation",
    "cryptocurrency market volatility analysis",
    "ESG investing performance metrics",
    "IPO market conditions and timing",
    "corporate bond yield spreads",
    "inflation hedging strategies",
    "emerging market debt risk assessment",
    "disaster recovery for stateful applications",
    "blue-green deployments across regions",
    "cost optimization for GPU workloads",
    "cross-region database replication",
    "edge computing architecture patterns",
    "serverless vs container trade-offs",
    "API gateway design patterns",
    "event-driven microservices architecture",
    "data lakehouse architecture",
    "real-time streaming with Kafka",
    "GitOps workflow with ArgoCD",
    "infrastructure as code with Terraform",
    "container image scanning and signing",
    "secrets rotation automation",
    "pipeline parallelism strategies",
    "canary deployment rollout strategies",
    "feature flag management systems",
    "load testing methodology and tools",
    "chaos engineering experiments",
    "observability with OpenTelemetry",
    "SQL query optimization techniques",
    "index design for high-throughput workloads",
    "connection pooling best practices",
    "sharding strategies for horizontal scaling",
    "read replica configuration",
    "backup and point-in-time recovery",
    "schema migration strategies",
    "time-series database selection",
    "graph database use cases",
    "full-text search implementation",
    "OpenAPI specification best practices",
    "versioning strategies for REST APIs",
    "GraphQL schema design patterns",
    "error handling and status codes",
    "rate limiting and throttling",
    "webhook design and reliability",
    "SDK generation from API specs",
    "API deprecation strategies",
    "pagination patterns for large datasets",
    "authentication flows for SPAs",
    "collaborative filtering algorithms",
    "content-based recommendation engines",
    "A/B testing statistical methods",
    "real-time feature stores",
    "model serving at scale with vLLM",
    "LLM inference optimization techniques",
    "KV cache management strategies",
    "prefix caching for shared prompts",
    "disaggregated prefill and decode",
    "GPU memory optimization for large models",
    "incident response runbook design",
    "SLO and error budget management",
    "capacity planning for inference workloads",
    "automated remediation workflows",
    "log aggregation pipeline design",
    "distributed tracing best practices",
    "alerting strategy and noise reduction",
    "game day exercise planning",
    "post-incident review processes",
    "on-call rotation best practices",
    "Python asyncio patterns and pitfalls",
    "Rust ownership and borrowing concepts",
    "Go concurrency with goroutines and channels",
    "TypeScript advanced type system features",
    "Java virtual threads and Project Loom",
    "WebAssembly use cases and limitations",
    "CUDA kernel optimization techniques",
    "Linux kernel tuning for performance",
    "container runtime security hardening",
    "eBPF for network observability",
]

ACTIONS = [
    "Explain in detail how",
    "Describe the best practices for",
    "Compare and contrast approaches to",
    "Walk through a step-by-step guide for",
    "Analyze the trade-offs involved in",
    "Outline a production-ready strategy for",
    "Identify common pitfalls when implementing",
    "Design a scalable solution for",
    "Troubleshoot common issues with",
    "Evaluate the performance implications of",
]

# ---------------------------------------------------------------------------
# Instrumented request function
# ---------------------------------------------------------------------------

def send_request(sys_prompt: str, user_prompt: str, verbose: bool = False) -> dict:
    if verbose:
        print(f"  [INPUT] system: {sys_prompt}")
        print(f"  [INPUT]   user: {user_prompt}")

    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=random.choice([64, 128, 200, 256]),
        temperature=random.uniform(0.5, 0.9),
    )

    if verbose:
        content = response.choices[0].message.content if response.choices else ""
        print(f"  [OUTPUT] {content}")

    usage = response.usage
    return {
        "completion_tokens": usage.completion_tokens if usage else 0,
        "prompt_tokens": usage.prompt_tokens if usage else 0,
    }


def run_load_generation(prompts: list, verbose: bool = False) -> None:
    num_prompts = len(prompts)
    print(f"Sending {num_prompts} prompt(s) with random delays (15-45s between requests)\n")

    success = 0
    errors = 0
    start = time.time()

    for i, (sys_prompt, user_prompt) in enumerate(prompts):
        print(f"\n--- Loop {i+1} of {num_prompts} ---")
        req_start = time.time()
        try:
            # Use a fresh context so every loop iteration starts a brand-new root trace.
            with tracer.start_as_current_span(
                "llm.request",
                kind=SpanKind.SERVER,
                context=Context(),
            ) as root_span:
                root_span.set_attribute("app.name", _app_name)
                root_span.set_attribute("gen_ai.request.model", LLM_MODEL)
                root_span.set_attribute("gen_ai.system", "vllm")
                root_span.set_attribute("server.address", VLLM_BASE_URL)
                root_span.set_attribute("llm.load_generator.iteration", i + 1)
                result = send_request(sys_prompt, user_prompt, verbose=verbose)

                if verbose:
                    ctx = root_span.get_span_context()
                    print(
                        "  [TRACE] "
                        f"trace_id={ctx.trace_id:032x} span_id={ctx.span_id:016x}"
                    )

            duration = time.time() - req_start
            tok = result["completion_tokens"]
            success += 1
            elapsed = time.time() - start
            rate = success / (elapsed / 3600)
            print(
                f"[{i+1}/{num_prompts}] SUCCESS tokens={tok} duration={duration:.2f}s "
                f"total_ok={success} err={errors} rate={rate:.0f}/hr"
            )
        except Exception as e:
            duration = time.time() - req_start
            errors += 1
            print(
                f"[{i+1}/{num_prompts}] FAILED  duration={duration:.2f}s error={e} "
                f"total_ok={success} err={errors}"
            )

        if i < num_prompts - 1:
            delay = random.uniform(15, 45)
            time.sleep(delay)

    elapsed = time.time() - start
    print(f"\nDone: {success} success, {errors} errors in {elapsed/3600:.1f} hours")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
parser = argparse.ArgumentParser(description="LLM load generator for vLLM endpoints")
parser.add_argument(
    "--num-prompts", type=int, default=1, metavar="INT",
    help="Number of prompts to send (default: 1, max: 10000)",
)
parser.add_argument(
    "--verbose", action="store_true", default=False,
    help="Print input prompts and output responses for each request",
)
args = parser.parse_args()
num_prompts = max(1, min(args.num_prompts, 10000))

prompts = []
for sys_prompt in SYSTEM_PROMPTS:
    for topic in TOPICS:
        for action in ACTIONS:
            prompts.append((sys_prompt, f"{action} {topic}."))

random.shuffle(prompts)
prompts = prompts[:num_prompts]

run_load_generation(prompts, verbose=args.verbose)

# Force-flush the OTLP batch exporter before the process exits
provider = trace.get_tracer_provider()
if hasattr(provider, "force_flush"):
    provider.force_flush(timeout_millis=10_000)
if hasattr(provider, "shutdown"):
    provider.shutdown()
