#!/bin/bash
# ==============================================================================
# Port-Forward Observability Services from Minikube (chatcraft namespace)
# ==============================================================================
# Usage: ./port-forwarding.sh
# Stop:  Ctrl+C (kills all background port-forwards)
# ==============================================================================

NAMESPACE="chatcraft"
CONTEXT="minikube"

echo "========================================"
echo "Port-forwarding observability services"
echo "Namespace: $NAMESPACE | Context: $CONTEXT"
echo "========================================"

kubectl port-forward -n $NAMESPACE svc/prometheus 9091:9090 --context=$CONTEXT &
echo "Prometheus      → http://localhost:9091"

kubectl port-forward -n $NAMESPACE svc/elasticsearch 9200:9200 --context=$CONTEXT &
echo "Elasticsearch   → http://localhost:9200"

kubectl port-forward -n $NAMESPACE svc/alertmanager 9093:9093 --context=$CONTEXT &
echo "Alertmanager    → http://localhost:9093"

kubectl port-forward -n $NAMESPACE svc/jaeger 16686:16686 --context=$CONTEXT &
echo "Jaeger          → http://localhost:16686"

kubectl port-forward -n $NAMESPACE svc/otel-collector 8888:8888 --context=$CONTEXT &
echo "OTel Collector  → http://localhost:8888"

echo ""
echo "All port-forwards running. Press Ctrl+C to stop all."
echo "========================================"

# Wait for all background jobs; Ctrl+C kills them all
trap "echo 'Stopping all port-forwards...'; kill 0" SIGINT SIGTERM
wait
