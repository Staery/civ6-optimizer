"""IO layer: map JSON (de)serialization. Future: Lua.log import, save parsing."""

from .map_schema import map_from_dict, map_to_dict, load_map, save_map

__all__ = ["map_from_dict", "map_to_dict", "load_map", "save_map"]
