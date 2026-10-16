from src.adapters.mangadex import MangaDexAdapter
from src.adapters.asura import AsuraAdapter
from src.adapters.komiku import KomikuAdapter
from src.adapters.vortex import VortexAdapter
from src.adapters.mgeko import MgekoAdapter

SITE_PRIORITY = {
    "MGEKO": 1,
    "MANGADEX": 2,
    "VORTEX": 3,
    "ASURA": 4,
    "KOMIKU": 5,
}

ADAPTER_CLASSES = {
    "MGEKO": MgekoAdapter,
    "MANGADEX": MangaDexAdapter,
    "VORTEX": VortexAdapter,
    "ASURA": AsuraAdapter,
    "KOMIKU": KomikuAdapter,
}
