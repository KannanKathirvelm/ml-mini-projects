"""Store registry: the single list the app iterates over.

To add a store, write an adapter subclassing `Store` and append it here.
"""
from stores.base import Offer, Store
from stores.dummyjson import DummyJSONStore
from stores.fakestore import FakeStoreAPIStore
from stores.simulated import SimulatedStore, simulated_stores


def all_stores() -> list[Store]:
    return [DummyJSONStore(), FakeStoreAPIStore(), *simulated_stores()]


__all__ = ["Offer", "Store", "SimulatedStore", "all_stores", "simulated_stores"]
