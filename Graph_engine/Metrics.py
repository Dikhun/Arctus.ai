from prometheus_client import Counter, Gauge, Histogram, Info

APP_INFO = Info("cge_app_info", "Application information")

graph_nodes_total = Gauge("cge_nodes_total", "Total nodes in graph")
graph_edges_total = Gauge("cge_edges_total", "Total edges in graph")

propagation_iterations = Histogram(
    "cge_propagation_iterations",
    "Iterations to convergence",
    buckets=[1, 2, 5, 10, 20, 50, 100],
)

query_duration = Histogram(
    "cge_query_duration_seconds",
    "Query latency",
    ["method"],
)

query_results_total = Counter(
    "cge_query_results_total",
    "Results returned",
    ["method"],
)

api_requests_total = Counter(
    "cge_api_requests_total",
    "Total API requests",
    ["method", "endpoint", "status"],
)
