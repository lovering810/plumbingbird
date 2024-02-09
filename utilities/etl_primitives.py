import json
import logging
import yaml
from pathlib import Path
from typing import Iterator


class Fetcher:

    def __init__(self) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)

    def fetch(self, *args, **kwargs):
        raise NotImplementedError("This method must be defined in a child class.")


class Buffer:

    def __init__(self, iter: Iterator, keymap_loc: Path) -> None:
        self.iter = iter
        self.keymap = self.load_keymap(keymap_loc) or {}

    @staticmethod
    def load_keymap(keymap_loc: Path = None) -> dict:
        if not keymap_loc:
            return None
        map_suffix = keymap_loc.suffix
        if map_suffix == ".yaml" or map_suffix == ".yml":
            load_op = yaml.safe_load_all
        elif map_suffix == ".json":
            load_op = json.load
        else:
            raise NotImplementedError(f"No read method known for {map_suffix}")
        with open(keymap_loc, "r") as fyle:
            keymap = dict(load_op(fyle))
        return keymap

    def map_key(self, field_name):
        return self.keymap.get(field_name, field_name)

    def process(self, field_value: str, *args, **kwargs) -> str:
        return field_value


class Loader:

    def __init__(self) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)

    def load(self, *args, **kwargs):
        raise NotImplementedError("This method must be defined in a child class.")
