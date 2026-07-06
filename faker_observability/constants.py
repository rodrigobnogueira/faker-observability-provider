"""Flat (uncorrelated) data pools and weighted tables.

Weighted tables are ``OrderedDict`` because Faker's ``random_elements``
requires an OrderedDict for weighted sampling, and every weighted draw in
this package goes through ``ObservabilityProvider._weighted`` with
``use_weighting=True`` (see AGENTS.md — weights are silently ignored
otherwise for providers registered via ``add_provider``).
"""

from collections import OrderedDict


LOG_LEVELS: OrderedDict[str, float] = OrderedDict(
    [
        ("DEBUG", 0.08),
        ("INFO", 0.70),
        ("WARN", 0.13),
        ("ERROR", 0.08),
        ("FATAL", 0.01),
    ]
)

HTTP_STATUSES: OrderedDict[int, float] = OrderedDict(
    [
        (200, 0.62),
        (201, 0.05),
        (204, 0.04),
        (301, 0.02),
        (302, 0.02),
        (304, 0.05),
        (400, 0.03),
        (401, 0.02),
        (403, 0.01),
        (404, 0.08),
        (429, 0.01),
        (500, 0.02),
        (502, 0.01),
        (503, 0.01),
        (504, 0.01),
    ]
)

HTTP_METHODS: OrderedDict[str, float] = OrderedDict(
    [
        ("GET", 0.68),
        ("POST", 0.18),
        ("PUT", 0.05),
        ("DELETE", 0.04),
        ("PATCH", 0.03),
        ("HEAD", 0.01),
        ("OPTIONS", 0.01),
    ]
)

SAMPLED_FLAGS: OrderedDict[str, float] = OrderedDict([("01", 0.90), ("00", 0.10)])

HTTP_5XX: tuple[int, ...] = (500, 502, 503)

GRPC_ERROR_CODES: tuple[int, ...] = (2, 4, 13, 14)  # UNKNOWN, DEADLINE_EXCEEDED, INTERNAL, UNAVAILABLE

EXCEPTION_TYPES: dict[str, tuple[str, ...]] = {
    "python": (
        "TimeoutError",
        "ValueError",
        "KeyError",
        "ConnectionError",
        "RuntimeError",
        "sqlalchemy.exc.OperationalError",
        "elasticsearch.ConnectionError",
    ),
    "java": (
        "java.lang.NullPointerException",
        "java.net.SocketTimeoutException",
        "java.lang.IllegalStateException",
        "com.mongodb.MongoTimeoutException",
        "org.springframework.dao.DataAccessResourceFailureException",
        "java.util.concurrent.TimeoutException",
    ),
    "javascript": (
        "TypeError",
        "RangeError",
        "ECONNREFUSED",
        "ETIMEDOUT",
        "ERR_UNHANDLED_REJECTION",
    ),
    "go": (
        "context deadline exceeded",
        "connection refused",
        "runtime error: invalid memory address or nil pointer dereference",
        "i/o timeout",
    ),
}

LOG_MESSAGES: dict[str, tuple[str, ...]] = {
    "DEBUG": (
        "acquired database connection from pool",
        "cache lookup for session token",
        "request headers parsed successfully",
        "feature flag evaluated",
        "connection returned to pool",
    ),
    "INFO": (
        "request completed successfully",
        "user session created",
        "order state transition applied",
        "payment authorization accepted",
        "cache refreshed from upstream",
        "scheduled task finished",
        "message published to broker",
    ),
    "WARN": (
        "retrying request after transient failure (attempt 2/3)",
        "response time above threshold",
        "cache miss rate elevated",
        "deprecated endpoint invoked",
        "connection pool nearing capacity",
    ),
    "ERROR": (
        "request failed after retries",
        "upstream dependency returned an error",
        "database query failed",
        "message delivery failed",
        "unhandled exception while processing request",
    ),
    "FATAL": (
        "unable to bind listener port, shutting down",
        "database connection pool exhausted, terminating",
        "configuration invalid at startup",
    ),
}

K8S_NAMESPACES: tuple[str, ...] = (
    "production",
    "staging",
    "default",
    "payments",
    "checkout",
    "monitoring",
    "logging",
    "kube-system",
    "ingress-nginx",
    "cert-manager",
)

# The alphabet Kubernetes uses for generated name suffixes
# (k8s.io/apimachinery/pkg/util/rand — vowels and confusable chars removed).
K8S_RAND_ALPHABET: str = "bcdfghjklmnpqrstvwxz2456789"

CONTAINER_REGISTRIES: tuple[str, ...] = (
    "docker.io",
    "ghcr.io",
    "gcr.io",
    "123456789012.dkr.ecr.us-east-1.amazonaws.com",
    "registry.gitlab.com",
)

REGISTRY_ORGS: tuple[str, ...] = ("acme", "shopcorp", "platform", "infra")

# cloud -> region -> zone suffixes. Zone string formats follow each
# provider's documented convention (AWS "<region><letter>", GCP
# "<region>-<letter>", Azure "<region>-<number>").
CLOUD_ZONES: dict[str, dict[str, tuple[str, ...]]] = {
    "aws": {
        "us-east-1": ("a", "b", "c"),
        "us-west-2": ("a", "b", "c"),
        "eu-west-1": ("a", "b", "c"),
        "sa-east-1": ("a", "b", "c"),
    },
    "gcp": {
        "us-central1": ("a", "b", "c"),
        "europe-west1": ("b", "c", "d"),
        "southamerica-east1": ("a", "b", "c"),
    },
    "azure": {
        "eastus": ("1", "2", "3"),
        "westeurope": ("1", "2", "3"),
        "brazilsouth": ("1", "2", "3"),
    },
}

# language -> telemetry.sdk.language (OTel semconv values; JS runtime is "nodejs").
SDK_LANGUAGES: dict[str, str] = {
    "python": "python",
    "java": "java",
    "javascript": "nodejs",
    "go": "go",
    "native": "cpp",
}

USER_AGENTS: tuple[str, ...] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148",
    "curl/8.5.0",
    "python-requests/2.32.0",
    "Go-http-client/2.0",
    "kube-probe/1.31",
    "Prometheus/2.53.0",
)

PROBE_USER_AGENTS: tuple[str, ...] = ("kube-probe/1.31", "Prometheus/2.53.0")

STATIC_ASSET_PATHS: tuple[str, ...] = (
    "/static/app.css",
    "/static/app.js",
    "/static/logo.svg",
    "/favicon.ico",
    "/robots.txt",
)

PROBE_PATHS: tuple[str, ...] = ("/healthz", "/metrics")

REFERERS: tuple[str, ...] = (
    "-",
    "-",
    "-",
    "https://shop.example.com/",
    "https://shop.example.com/products",
    "https://www.google.com/",
)

APACHE_ERROR_MODULES: tuple[str, ...] = ("core", "proxy", "ssl", "rewrite", "mpm_event")

APACHE_ERROR_MESSAGES: tuple[str, ...] = (
    "AH01071: Got error 'Primary script unknown'",
    "AH00558: Could not reliably determine the server's fully qualified domain name",
    "AH01114: HTTP: failed to make connection to backend",
    "AH02032: Hostname provided via SNI and hostname provided via HTTP have no compatible SSL setup",
    "AH00126: Invalid URI in request",
)

NGINX_ERROR_MESSAGES: tuple[str, ...] = (
    "connect() failed (111: Connection refused) while connecting to upstream",
    "upstream timed out (110: Connection timed out) while reading response header from upstream",
    "no live upstreams while connecting to upstream",
    'open() "/usr/share/nginx/html/missing.html" failed (2: No such file or directory)',
)

# W3C tracestate vendor keys (spec-style short vendor tokens).
TRACESTATE_VENDOR_KEYS: tuple[str, ...] = ("rojo", "congo", "acme", "es", "dd")

# level -> syslog severity; PRI = facility(16, local0) * 8 + severity.
SYSLOG_SEVERITIES: dict[str, int] = {
    "FATAL": 2,
    "ERROR": 3,
    "WARN": 4,
    "INFO": 6,
    "DEBUG": 7,
}

SYSLOG_FACILITY: int = 16

# Stack-frame pools per language: (function, file, line-range) building blocks.
PYTHON_APP_FRAMES: tuple[tuple[str, str], ...] = (
    ("process_order", "/app/app/handlers/orders.py"),
    ("charge_payment", "/app/app/handlers/payments.py"),
    ("fetch_user", "/app/app/handlers/users.py"),
    ("call_upstream", "/app/app/services/client.py"),
)

PYTHON_LIB_FRAMES: tuple[tuple[str, str], ...] = (
    ("send", "/usr/local/lib/python3.12/site-packages/requests/adapters.py"),
    ("urlopen", "/usr/local/lib/python3.12/site-packages/urllib3/connectionpool.py"),
    ("execute", "/usr/local/lib/python3.12/site-packages/sqlalchemy/engine/base.py"),
)

JAVA_APP_FRAMES: tuple[tuple[str, str], ...] = (
    ("com.acme.orders.OrderService.process", "OrderService.java"),
    ("com.acme.payments.PaymentClient.charge", "PaymentClient.java"),
    ("com.acme.checkout.CheckoutController.submit", "CheckoutController.java"),
    ("com.acme.common.RetryTemplate.execute", "RetryTemplate.java"),
)

JAVA_FRAMEWORK_FRAMES: tuple[tuple[str, str], ...] = (
    ("org.springframework.web.servlet.DispatcherServlet.doDispatch", "DispatcherServlet.java"),
    ("jakarta.servlet.http.HttpServlet.service", "HttpServlet.java"),
    ("org.apache.catalina.core.ApplicationFilterChain.doFilter", "ApplicationFilterChain.java"),
)

JAVASCRIPT_APP_FRAMES: tuple[tuple[str, str], ...] = (
    ("processOrder", "/app/src/routes/orders.js"),
    ("chargePayment", "/app/src/routes/payments.js"),
    ("request", "/app/src/lib/http.js"),
)

JAVASCRIPT_LIB_FRAMES: tuple[tuple[str, str], ...] = (
    ("next", "/app/node_modules/express/lib/router/index.js"),
    ("processTicksAndRejections", "node:internal/process/task_queues"),
    ("Object.<anonymous>", "/app/src/index.js"),
)

GO_FRAMES: tuple[tuple[str, str], ...] = (
    ("main.processOrder", "/app/internal/orders/handler.go"),
    ("main.(*Server).handleCheckout", "/app/internal/server/server.go"),
    ("github.com/acme/shop/pkg/db.Query", "/app/pkg/db/db.go"),
    ("net/http.(*conn).serve", "/usr/local/go/src/net/http/server.go"),
)
