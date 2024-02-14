import pytest
from collections.abc import Iterator
from pathlib import Path
from ...etl.transformers.csv_streamer import CSVBuffer
from ..demo.dummy_api_fetcher import DummyJSON
from ...utilities.streamer import StringIteratorIO


@pytest.fixture
def stringyboi():
    iter = (s for s in ["first", "next", "last"])
    return StringIteratorIO(iter)


@pytest.fixture
def etl_buffer():
    fetcher = DummyJSON(endpoint="products", parse_key="products")
    keymap_loc = Path(__file__).parents[1] / "product_map.json"
    fetchiter = fetcher.fetch()
    return CSVBuffer(iter=fetchiter, keymap_loc=keymap_loc)


def test_stringy(stringyboi):
    assert isinstance(stringyboi, Iterator)
    assert stringyboi.read() == "firstnextlast"


def test_process(etl_buffer):

    result = etl_buffer.process(field_name="id", field_value="id")
    assert result is None


def test_buff(etl_buffer):

    iter = etl_buffer.get_buffer(fields=["title", "description", "discountPercentage"])
    assert isinstance(iter, Iterator)
    firstprod = "iPhone 9`An apple mobile which is nothing like apple`12.96\n"
    assert iter._read1() == firstprod


def test_get_all(etl_buffer):

    fields = [
        "id",
        "title",
        "description",
        "price",
        "discountPercentage",
        "rating",
        "stock",
        "brand",
        "category",
        "thumbnail",
    ]

    output = etl_buffer.get_buffer(fields=fields).read()
    assert len(output.split("\n")) == 101
