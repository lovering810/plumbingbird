from pathlib import Path
from typing import Iterator

from ...utilities.etl_primitives import Buffer
from ...utilities.streamer import StringIteratorIO


class CSVBuffer(Buffer):

    def __init__(self, iter: Iterator, keymap_loc: Path = None) -> None:
        super().__init__(iter, keymap_loc)

    @staticmethod
    def clean_value(value: str = None) -> str:
        """
        CSV-specific string revision for values to ensure null values and
        newlines in content are correctly handled.

        :param value str: value to be a CSV cell
        :return str: CSV-friendly version of the value
        """
        if value is None:
            return r"\N"
        return str(value).replace("\n", "\\n")

    def process(self, field_name: str, field_value: str):
        """
        Generic function for using field_name to assign logic
        to apply to a field_value.
        Defaults to returning the same value that is given.

        :param field_name str: name of the field in the results to which this value belongs.
        :param field_value str: value of field for this record
        """
        # TODO: genericize/build out
        match field_name:
            case "id":
                if field_value == "id":
                    return None
                else:
                    return field_value
            case _:
                return field_value

    def get_buffer(self, fields: list, delim: str = "`") -> Iterator:
        """
        Wraps the class input iterator (of dicts) in additional processing and
        formatting to make it behave like a CSV.

        :param fields list: list of fields for each record to include in the
        output CSV
        :param delim str: the delimiter to use in the output CSV, defaults to "`"
        """
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
