"""Correlated service-topology catalog: 20 services (15 application + 5 infrastructure).

The dependency graph is a DAG (enforced by tests/test_catalog.py). Operation
names follow the OpenTelemetry semantic conventions exactly:

- HTTP server spans:   "{method} {route}"          (route templates kept)
- gRPC spans:          "/{package}.{Service}/{Method}"
- Database spans:      "{operation} {target}"       (bare command for Redis)
- Messaging producer:  "publish {destination}"

``error_types`` entries must be a subset of ``EXCEPTION_TYPES[language]`` in
constants.py (also test-enforced). Infrastructure services (language
"native") emit no exceptions of their own — a failed call to them is
attributed to the calling service's language.
"""

from .types import ServiceData


SERVICE_CORRELATIONS: dict[str, ServiceData] = {
    "api-gateway": {
        "kind": "http",
        "language": "go",
        "version": "3.2.1",
        "operations": [
            "GET /api/products/{id}",
            "GET /api/products",
            "POST /api/checkout",
            "GET /api/orders/{id}",
            "GET /api/search",
            "GET /api/recommendations/{user_id}",
            "POST /api/auth/token",
            "GET /api/users/{id}",
            "GET /api/cart/{id}",
        ],
        "dependencies": [
            "auth-service",
            "user-service",
            "product-service",
            "search-service",
            "checkout-service",
            "recommendation-service",
        ],
        "latency_ms": (3.0, 15.0),
        "error_types": ["context deadline exceeded", "connection refused"],
    },
    "auth-service": {
        "kind": "http",
        "language": "go",
        "version": "1.9.0",
        "operations": ["POST /auth/token", "GET /auth/verify"],
        "dependencies": ["postgres", "redis"],
        "latency_ms": (4.0, 20.0),
        "error_types": [
            "runtime error: invalid memory address or nil pointer dereference",
            "context deadline exceeded",
        ],
    },
    "user-service": {
        "kind": "http",
        "language": "java",
        "version": "2.4.1",
        "operations": ["GET /users/{id}", "PUT /users/{id}"],
        "dependencies": ["postgres", "redis"],
        "latency_ms": (8.0, 60.0),
        "error_types": ["java.lang.NullPointerException", "java.net.SocketTimeoutException"],
    },
    "product-service": {
        "kind": "http",
        "language": "java",
        "version": "2.1.3",
        "operations": ["GET /products/{id}", "GET /products"],
        "dependencies": ["mongodb", "redis"],
        "latency_ms": (8.0, 55.0),
        "error_types": ["java.lang.IllegalStateException", "com.mongodb.MongoTimeoutException"],
    },
    "search-service": {
        "kind": "http",
        "language": "python",
        "version": "1.5.2",
        "operations": ["GET /search"],
        "dependencies": ["elasticsearch"],
        "latency_ms": (12.0, 90.0),
        "error_types": ["TimeoutError", "elasticsearch.ConnectionError"],
    },
    "recommendation-service": {
        "kind": "http",
        "language": "python",
        "version": "0.9.4",
        "operations": ["GET /recommendations/{user_id}"],
        "dependencies": ["mongodb", "redis"],
        "latency_ms": (15.0, 110.0),
        "error_types": ["KeyError", "ValueError"],
    },
    "checkout-service": {
        "kind": "http",
        "language": "java",
        "version": "4.0.2",
        "operations": ["POST /checkout"],
        "dependencies": ["cart-service", "payment-service", "inventory-service", "order-service"],
        "latency_ms": (10.0, 70.0),
        "error_types": ["java.lang.IllegalStateException", "java.net.SocketTimeoutException"],
    },
    "cart-service": {
        "kind": "http",
        "language": "javascript",
        "version": "1.3.7",
        "operations": ["GET /cart/{id}", "POST /cart/{id}/items"],
        "dependencies": ["redis"],
        "latency_ms": (6.0, 40.0),
        "error_types": ["TypeError", "ECONNREFUSED"],
    },
    "payment-service": {
        "kind": "http",
        "language": "java",
        "version": "5.1.0",
        "operations": ["POST /payments"],
        "dependencies": ["fraud-service", "postgres", "kafka"],
        "latency_ms": (20.0, 150.0),
        "error_types": [
            "java.net.SocketTimeoutException",
            "org.springframework.dao.DataAccessResourceFailureException",
        ],
    },
    "fraud-service": {
        "kind": "http",
        "language": "python",
        "version": "2.0.1",
        "operations": ["POST /fraud/score"],
        "dependencies": ["postgres"],
        "latency_ms": (25.0, 200.0),
        "error_types": ["ValueError", "TimeoutError"],
    },
    "inventory-service": {
        "kind": "grpc",
        "language": "go",
        "version": "1.7.3",
        "operations": [
            "/inventory.InventoryService/CheckStock",
            "/inventory.InventoryService/ReserveItems",
        ],
        "dependencies": ["postgres", "redis"],
        "latency_ms": (5.0, 25.0),
        "error_types": ["context deadline exceeded"],
    },
    "order-service": {
        "kind": "http",
        "language": "python",
        "version": "3.3.0",
        "operations": ["POST /orders", "GET /orders/{id}"],
        "dependencies": ["postgres", "shipping-service", "notification-service", "kafka"],
        "latency_ms": (10.0, 80.0),
        "error_types": ["sqlalchemy.exc.OperationalError", "KeyError"],
    },
    "shipping-service": {
        "kind": "http",
        "language": "go",
        "version": "1.2.5",
        "operations": ["POST /shipments"],
        "dependencies": ["postgres", "kafka"],
        "latency_ms": (6.0, 35.0),
        "error_types": ["connection refused", "i/o timeout"],
    },
    "notification-service": {
        "kind": "http",
        "language": "javascript",
        "version": "2.2.0",
        "operations": ["POST /notifications"],
        "dependencies": ["redis", "kafka"],
        "latency_ms": (5.0, 30.0),
        "error_types": ["ETIMEDOUT", "TypeError"],
    },
    # Kafka consumer; CONSUMER span continuation is on the roadmap, so it has
    # no synchronous dependencies in v1.
    "email-worker": {
        "kind": "worker",
        "language": "javascript",
        "version": "1.1.2",
        "operations": ["process notifications"],
        "dependencies": [],
        "latency_ms": (30.0, 250.0),
        "error_types": ["ETIMEDOUT"],
    },
    "postgres": {
        "kind": "db",
        "language": "native",
        "version": "16.4",
        "operations": [
            "SELECT shop.orders",
            "INSERT shop.orders",
            "SELECT shop.users",
            "UPDATE shop.inventory",
            "SELECT shop.payments",
        ],
        "dependencies": [],
        "latency_ms": (2.0, 30.0),
        "error_types": [],
    },
    "redis": {
        "kind": "cache",
        "language": "native",
        "version": "7.4.0",
        "operations": ["GET", "SET", "HGETALL", "EXPIRE"],
        "dependencies": [],
        "latency_ms": (0.3, 2.0),
        "error_types": [],
    },
    "mongodb": {
        "kind": "db",
        "language": "native",
        "version": "7.0.12",
        "operations": ["find catalog.products", "insert catalog.reviews"],
        "dependencies": [],
        "latency_ms": (3.0, 40.0),
        "error_types": [],
    },
    "elasticsearch": {
        "kind": "db",
        "language": "native",
        "version": "8.15.1",
        "operations": ["search products"],
        "dependencies": [],
        "latency_ms": (10.0, 120.0),
        "error_types": [],
    },
    "kafka": {
        "kind": "queue",
        "language": "native",
        "version": "3.8.0",
        "operations": ["publish orders", "publish payments", "publish notifications"],
        "dependencies": [],
        "latency_ms": (2.0, 15.0),
        "error_types": [],
    },
}
