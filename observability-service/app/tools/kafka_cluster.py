"""
Kafka cluster tool — queries cluster metadata via the Kafka Admin API.

This tool answers STRUCTURAL questions about a Kafka cluster: topics, partitions,
replicas, leaders, ISRs (in-sync replicas), brokers, controller, and consumer
groups. For NUMERIC metrics (throughput, request latency, ISR shrink rate, JVM
heap, GC, under-replicated count), the LLM should use the existing
`prometheus_query` tool against the JMX exporter (metrics prefixed `kafka_*`).
The system prompt teaches the LLM this routing rule.

Mirrors the structural pattern of `k8s_resources.py`: one tool, action enum,
match dispatch, private helper per action, uniform error string returns.
"""
import logging
from typing import Type, Optional

from pydantic import BaseModel, ConfigDict, Field
from langchain_core.tools import BaseTool

from .base import BackendConfig

logger = logging.getLogger(__name__)


class KafkaClusterInput(BaseModel):
    """Input for the Kafka cluster tool."""
    action: str = Field(
        description=(
            "Action to perform: 'list_topics', 'describe_topic' (requires topic_name), "
            "'list_brokers', 'list_consumer_groups', 'describe_consumer_group' "
            "(requires group_id), or 'cluster_health'."
        )
    )
    topic_name: Optional[str] = Field(
        default=None,
        description="Topic name. Required for action='describe_topic'.",
    )
    group_id: Optional[str] = Field(
        default=None,
        description="Consumer group id. Required for action='describe_consumer_group'.",
    )


class KafkaClusterTool(BaseTool):
    """Query Kafka cluster metadata via the Kafka Admin API.

    Use this tool for STRUCTURAL questions about the cluster — topics, partitions,
    replicas, leaders, ISRs, brokers, controller, and consumer groups. NOT for
    numeric metrics like throughput or latency, which live in Prometheus.
    """
    name: str = "kafka_cluster"
    description: str = (
        "Query Kafka cluster metadata via the Kafka Admin API. Use this tool for "
        "STRUCTURAL questions about the cluster — topics, partitions, replicas, "
        "leaders, ISRs (in-sync replicas), brokers, controller, consumer groups, "
        "and consumer group lag. "
        "DO NOT use this tool for numeric metrics like throughput, request latency, "
        "ISR shrink rate, JVM heap, or GC pauses — those are exposed by the JMX "
        "exporter and queryable via prometheus_query (metric prefix kafka_*). "
        "Actions: "
        "'list_topics' (enumerate all topics with partition counts), "
        "'describe_topic' (requires topic_name; returns per-partition leader, "
        "replicas, and ISR — use for 'who is the leader for topic X partition Y' "
        "or 'is partition Z under-replicated'), "
        "'list_brokers' (broker id, host, port, and which broker is the active "
        "controller), "
        "'list_consumer_groups' (enumerate all consumer groups), "
        "'describe_consumer_group' (requires group_id; returns members, partition "
        "assignments, committed offsets, log-end offsets, and lag), "
        "'cluster_health' (high-level snapshot — broker count, controller, topic "
        "and partition counts, and any under-replicated partitions)."
    )
    args_schema: Type[BaseModel] = KafkaClusterInput
    config: BackendConfig
    model_config = ConfigDict(arbitrary_types_allowed=True)

    # ── Connection helper ──

    def _bootstrap_servers(self) -> list:
        """Split the configured URL on commas to a bootstrap.servers list.

        Defensively strips http:// or https:// scheme prefixes (and any trailing
        path) so a user typing `http://kafka:9092` in the admin form's URL field
        does not produce an opaque kafka-python parse error at runtime.
        """
        if not self.config.url:
            raise ValueError("Kafka backend has no bootstrap servers configured (url is empty)")
        out = []
        for raw in self.config.url.split(","):
            s = raw.strip()
            if not s:
                continue
            for prefix in ("http://", "https://"):
                if s.lower().startswith(prefix):
                    s = s[len(prefix):]
                    break
            if "/" in s:
                s = s.split("/", 1)[0]
            out.append(s)
        return out

    def _get_admin_client(self):
        """Construct a KafkaAdminClient from the backend config.

        v1 supports auth_type='none' only. SASL/PLAIN, SASL/SCRAM, and mTLS are
        deferred — when added, populate `security_protocol`, `sasl_mechanism`,
        `sasl_plain_username`, `sasl_plain_password`, etc. from
        `self.config.credentials`.

        Both `request_timeout_ms` and `api_version_auto_timeout_ms` are derived
        from `self.config.timeout_seconds` with a 10-second floor. The latter
        gates kafka-python's bootstrap-handshake API-version probe; the default
        of 2000ms is too short for some brokers and causes the bootstrap to
        abort with NoBrokersAvailable before metadata is ever returned.
        """
        from kafka.admin import KafkaAdminClient

        timeout_ms = max(int(self.config.timeout_seconds * 1000), 10000)
        kwargs = {
            "bootstrap_servers": self._bootstrap_servers(),
            "client_id": "chatcraft-observability",
            "request_timeout_ms": timeout_ms,
            "api_version_auto_timeout_ms": timeout_ms,
        }
        if self.config.auth_type and self.config.auth_type != "none":
            # Stub for future SASL/TLS support — see plan "Out of scope".
            raise NotImplementedError(
                f"Kafka auth_type '{self.config.auth_type}' is not yet supported. "
                "v1 only supports auth_type='none'."
            )
        return KafkaAdminClient(**kwargs)

    def _get_consumer_for_offsets(self):
        """Construct a KafkaConsumer used only for end_offsets() lag computation.

        kafka-python's AdminClient does not expose log-end offsets directly, so we
        use a transient KafkaConsumer purely as an offset reader. Same auth rules
        as the AdminClient.
        """
        from kafka import KafkaConsumer

        timeout_ms = max(int(self.config.timeout_seconds * 1000), 10000)
        kwargs = {
            "bootstrap_servers": self._bootstrap_servers(),
            "client_id": "chatcraft-observability-lag",
            "consumer_timeout_ms": 5000,
            "request_timeout_ms": timeout_ms,
            "api_version_auto_timeout_ms": timeout_ms,
            "enable_auto_commit": False,
        }
        if self.config.auth_type and self.config.auth_type != "none":
            raise NotImplementedError(
                f"Kafka auth_type '{self.config.auth_type}' is not yet supported."
            )
        return KafkaConsumer(**kwargs)

    # ── Dispatch ──

    def _run(
        self,
        action: str,
        topic_name: Optional[str] = None,
        group_id: Optional[str] = None,
    ) -> str:
        """Dispatch on action and return a markdown-friendly string."""
        try:
            admin = self._get_admin_client()
        except ImportError:
            return "kafka-python not installed. Install with: pip install kafka-python"
        except NotImplementedError as e:
            return f"Kafka query error: {e}"
        except Exception as e:
            return f"Cannot connect to Kafka at {self.config.url}: {e}"

        try:
            match action:
                case "list_topics":
                    return self._list_topics(admin)
                case "describe_topic":
                    if not topic_name:
                        return "describe_topic requires the 'topic_name' parameter."
                    return self._describe_topic(admin, topic_name)
                case "list_brokers":
                    return self._list_brokers(admin)
                case "list_consumer_groups":
                    return self._list_consumer_groups(admin)
                case "describe_consumer_group":
                    if not group_id:
                        return "describe_consumer_group requires the 'group_id' parameter."
                    return self._describe_consumer_group(admin, group_id)
                case "cluster_health":
                    return self._cluster_health(admin)
                case _:
                    return (
                        f"Unsupported action: {action}. Supported: list_topics, "
                        "describe_topic, list_brokers, list_consumer_groups, "
                        "describe_consumer_group, cluster_health."
                    )
        except Exception as e:
            logger.exception("Kafka %s failed", action)
            return f"Kafka query error ({action}): {e}"
        finally:
            try:
                admin.close()
            except Exception:
                pass

    # ── Action implementations ──

    def _list_topics(self, admin) -> str:
        topics = sorted(admin.list_topics())
        # Filter out internal __consumer_offsets and similar from the headline
        # but still include them in a separate section so the LLM can see them.
        user_topics = [t for t in topics if not t.startswith("__")]
        internal_topics = [t for t in topics if t.startswith("__")]

        # Get partition counts via describe_topics for the user topics
        details = admin.describe_topics(user_topics) if user_topics else []
        partition_counts = {d["topic"]: len(d.get("partitions", [])) for d in details}

        out = [f"Kafka topics ({len(topics)} total, {len(user_topics)} user):"]
        if user_topics:
            for t in user_topics:
                out.append(f"  - {t} (partitions: {partition_counts.get(t, '?')})")
        else:
            out.append("  (no user topics)")
        if internal_topics:
            out.append(f"Internal topics ({len(internal_topics)}): {', '.join(internal_topics)}")
        return "\n".join(out)

    def _describe_topic(self, admin, topic_name: str) -> str:
        details = admin.describe_topics([topic_name])
        if not details:
            return f"Topic '{topic_name}' not found."

        topic = details[0]
        if topic.get("error_code", 0) != 0:
            return f"Topic '{topic_name}' lookup error code: {topic.get('error_code')}"

        partitions = topic.get("partitions", [])
        out = [
            f"Topic: {topic_name}",
            f"Partition count: {len(partitions)}",
            "",
            "Per-partition assignment (partition | leader | replicas | ISR | under-replicated):",
        ]
        under_replicated = 0
        for p in sorted(partitions, key=lambda x: x.get("partition", 0)):
            pid = p.get("partition", "?")
            leader = p.get("leader", "?")
            replicas = p.get("replicas", []) or []
            isr = p.get("isr", []) or []
            ur = len(isr) < len(replicas)
            if ur:
                under_replicated += 1
            out.append(
                f"  [{pid}] leader={leader}, replicas={replicas}, isr={isr}"
                f"{', UNDER-REPLICATED' if ur else ''}"
            )

        if under_replicated:
            out.append("")
            out.append(f"WARNING: {under_replicated} partition(s) under-replicated.")
        return "\n".join(out)

    def _list_brokers(self, admin) -> str:
        cluster = admin.describe_cluster()
        brokers = cluster.get("brokers", []) or []
        controller_id = cluster.get("controller_id", "?")
        cluster_id = cluster.get("cluster_id", "?")

        out = [
            f"Kafka cluster id: {cluster_id}",
            f"Active controller broker id: {controller_id}",
            f"Brokers ({len(brokers)}):",
        ]
        for b in sorted(brokers, key=lambda x: x.get("node_id", 0)):
            node_id = b.get("node_id", "?")
            host = b.get("host", "?")
            port = b.get("port", "?")
            rack = b.get("rack")
            controller_marker = " (controller)" if node_id == controller_id else ""
            rack_str = f", rack={rack}" if rack else ""
            out.append(f"  - id={node_id}, host={host}:{port}{rack_str}{controller_marker}")
        return "\n".join(out)

    def _list_consumer_groups(self, admin) -> str:
        groups = admin.list_consumer_groups()
        if not groups:
            return "No consumer groups found."

        out = [f"Consumer groups ({len(groups)}):"]
        for g in sorted(groups, key=lambda x: x[0] if isinstance(x, tuple) else str(x)):
            # list_consumer_groups returns list of (group_id, protocol_type) tuples
            if isinstance(g, tuple) and len(g) >= 2:
                gid, ptype = g[0], g[1]
                out.append(f"  - {gid} (protocol_type={ptype})")
            else:
                out.append(f"  - {g}")
        return "\n".join(out)

    def _describe_consumer_group(self, admin, group_id: str) -> str:
        descriptions = admin.describe_consumer_groups([group_id])
        if not descriptions:
            return f"Consumer group '{group_id}' not found."

        desc = descriptions[0]
        # kafka-python returns a GroupInformation namedtuple-like with attrs
        state = getattr(desc, "state", "?")
        protocol = getattr(desc, "protocol", "?")
        protocol_type = getattr(desc, "protocol_type", "?")
        members = list(getattr(desc, "members", []) or [])

        out = [
            f"Consumer group: {group_id}",
            f"State: {state}",
            f"Protocol: {protocol} (type={protocol_type})",
            f"Member count: {len(members)}",
        ]

        # Member details
        if members:
            out.append("")
            out.append("Members:")
            for m in members:
                mid = getattr(m, "member_id", "?")
                client_id = getattr(m, "client_id", "?")
                host = getattr(m, "client_host", "?")
                out.append(f"  - {mid} (client_id={client_id}, host={host})")

        # Committed offsets + lag (best-effort — failures here don't block the
        # rest of the response)
        try:
            offsets = admin.list_consumer_group_offsets(group_id) or {}
            if offsets:
                out.append("")
                out.append("Partition offsets and lag:")
                end_offsets = self._end_offsets_for(list(offsets.keys()))
                total_lag = 0
                for tp, offset_meta in sorted(
                    offsets.items(),
                    key=lambda kv: (kv[0].topic, kv[0].partition),
                ):
                    committed = getattr(offset_meta, "offset", 0)
                    end = end_offsets.get(tp)
                    if end is not None:
                        lag = max(end - committed, 0)
                        total_lag += lag
                        out.append(
                            f"  - {tp.topic}[{tp.partition}]: committed={committed}, "
                            f"end={end}, lag={lag}"
                        )
                    else:
                        out.append(
                            f"  - {tp.topic}[{tp.partition}]: committed={committed}, "
                            "end=?, lag=?"
                        )
                out.append(f"Total lag (sum across partitions): {total_lag}")
        except Exception as e:
            out.append("")
            out.append(f"(Lag computation failed: {e})")

        return "\n".join(out)

    def _end_offsets_for(self, topic_partitions: list) -> dict:
        """Best-effort log-end offsets for the given partitions.

        Returns an empty dict on failure rather than raising — lag is best-effort.
        """
        if not topic_partitions:
            return {}
        consumer = None
        try:
            consumer = self._get_consumer_for_offsets()
            return consumer.end_offsets(topic_partitions) or {}
        except Exception as e:
            logger.warning("end_offsets() failed: %s", e)
            return {}
        finally:
            if consumer is not None:
                try:
                    consumer.close()
                except Exception:
                    pass

    def _cluster_health(self, admin) -> str:
        cluster = admin.describe_cluster()
        brokers = cluster.get("brokers", []) or []
        controller_id = cluster.get("controller_id", "?")

        topics = sorted(admin.list_topics())
        user_topics = [t for t in topics if not t.startswith("__")]
        details = admin.describe_topics(user_topics) if user_topics else []

        total_partitions = 0
        under_replicated = []  # list of (topic, partition_id, leader, replicas, isr)
        for d in details:
            t = d.get("topic")
            for p in d.get("partitions", []):
                total_partitions += 1
                replicas = p.get("replicas", []) or []
                isr = p.get("isr", []) or []
                if len(isr) < len(replicas):
                    under_replicated.append(
                        (t, p.get("partition"), p.get("leader"), replicas, isr)
                    )

        out = [
            "Kafka cluster health:",
            f"  Brokers: {len(brokers)}",
            f"  Controller broker id: {controller_id}",
            f"  Topics (user): {len(user_topics)}",
            f"  Topics (incl. internal): {len(topics)}",
            f"  Total partitions (user topics): {total_partitions}",
            f"  Under-replicated partitions: {len(under_replicated)}",
        ]
        if under_replicated:
            out.append("")
            out.append("Under-replicated detail:")
            for t, pid, leader, replicas, isr in under_replicated[:20]:
                out.append(
                    f"  - {t}[{pid}] leader={leader}, replicas={replicas}, isr={isr}"
                )
            if len(under_replicated) > 20:
                out.append(f"  ... and {len(under_replicated) - 20} more")
        else:
            out.append("")
            out.append("All partitions are fully in-sync.")
        return "\n".join(out)
