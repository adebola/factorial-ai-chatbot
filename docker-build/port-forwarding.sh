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

# Jaeger and OTel use offset ports to avoid conflict with Docker containers
# Docker Jaeger: localhost:16686 / localhost:4317
# Minikube Jaeger: localhost:26686 / OTel gRPC: localhost:14317
kubectl port-forward -n $NAMESPACE svc/jaeger 26686:16686 --context=$CONTEXT &
echo "Jaeger (mk)     → http://localhost:26686  (Docker Jaeger at :16686)"

kubectl port-forward -n $NAMESPACE svc/otel-collector 8888:8888 --context=$CONTEXT &
echo "OTel Metrics    → http://localhost:8888"

kubectl port-forward -n $NAMESPACE svc/otel-collector 14317:4317 --context=$CONTEXT &
echo "OTel gRPC (mk)  → localhost:14317  (Docker OTel at :4317)"

echo ""
echo "All port-forwards running. Press Ctrl+C to stop all."
echo "========================================"

# Wait for all background jobs; Ctrl+C kills them all
trap "echo 'Stopping all port-forwards...'; kill 0" SIGINT SIGTERM
wait
