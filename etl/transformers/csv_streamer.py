from pathlib import Path
from typing import Any, Iterator

from ..utilities.etl_primitives import Buffer
from ..utilities.streamer import StringIteratorIO


class CSVBuffer(Buffer):

    def __init__(self, iter: Iterator, keymap_loc: Path = None) -> None:
        super().__init__(iter, keymap_loc)

    @staticmethod
    def clean_value(value: Any = None) -> str:
        if value is None:
            return r"\N"
        return str(value).replace("\n", "\\n")

    def process(self, field_name: str, field_value: str):
        match field_name:
            case "id":
                if field_value == "id":
                    return None
                else:
                    return field_value
            case _:
                return field_value

    def get_buffer(self, fields: list, delim: str = "`") -> Iterator:
        item_iterator = StringIteratorIO(
            (
                delim.join(
                    map(
                        self.clean_value,
                        (
                            self.process(field_name, item.get(field_name))
                            for field_name in fields
                        ),
                    )
                )
                + "\n"
                for item in self.iter
            )
        )
        return item_iterator
