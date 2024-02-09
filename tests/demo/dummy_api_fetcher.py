from typing import Any
from ...extractors.api_fetcher import APIStreamFetcher

BASE_URL = "https://dummyjson.com"
DUMMY_AUTH = {"API_USER": "kminchelle", "API_PW": "0lelplR"}


class DummyJSON(APIStreamFetcher):

    def __init__(
        self,
        endpoint: str,
        parse_key: str = None,
        base_url: str = BASE_URL,
        auth: dict = DUMMY_AUTH,
    ) -> None:
        self.parse_key = parse_key
        super().__init__(endpoint=endpoint, base_url=base_url, auth=auth)

    def parse_response(self, response_json: dict) -> Any:
        return response_json.get(self.parse_key, response_json)

    def compose_url(self, limit, skip):
        return f"{self.base_url}/{self.endpoint}?limit={limit}&skip={skip}"
