import chromadb
from chromadb.config import Settings


c = chromadb.HttpClient(host="localhost", port=8100, settings=Settings(anonymized_telemetry=False, allow_reset=True))
print("Heartbeat: ", c.heartbeat())
print("Collections: ", c.list_collections())