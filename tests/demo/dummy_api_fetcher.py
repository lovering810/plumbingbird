from typing import Any
from extractors.api_fetcher import APIStreamFetcher


class DummyJSON(APIStreamFetcher):

    def __init__(
        self, endpoint: str, parse_key: str = None, base_url: str = None
    ) -> None:
        self.parse_key = parse_key
        super().__init__(endpoint, base_url)

    def parse_response(self, response_json: dict) -> Any:
        return response_json.get(self.parse_key, response_json)

    def compose_url(self, limit, skip):
        return f"{self.base_url}/{self.endpoint}?limit={limit}&skip={skip}"
