import requests
from typing import Any, Iterator
from utilities.etl_primitives import Fetcher
from utilities.environment import get_secret


class APIFetcher(Fetcher):

    def __init__(
        self,
        endpoint: str,
        parse_key: str = None,
        base_url: str = None,
    ) -> None:
        base_url = base_url or get_secret("BASE_URL")
        self.base_url = base_url
        self.endpoint = endpoint
        self.parse_key = parse_key
        super().__init__()

    def compose_url(self, limit, skip):
        """ """

        return f"{self.base_url}/{self.endpoint}?limit={limit}&skip={skip}"

    def connect(self):
        session = requests.Session()
        API_USER = get_secret("API_USER")
        API_PW = get_secret("API_PW")
        session.auth = (API_USER, API_PW)
        return session

    def fetch(self, *args, **kwargs):
        raise NotImplementedError("Must be defined in child class.")


class APIStreamFetcher(APIFetcher):

    def __init__(
        self, endpoint: str, parse_key: str = None, base_url: str = None
    ) -> None:
        super().__init__(endpoint, parse_key, base_url)

    def fetch_iter(self) -> Iterator[dict[str, Any]]:
        session = self.connect()
        skip = 0
        limit = 100
        while True:
            with session as sesh:
                response = sesh.get(self.compose_url(limit, skip))
                response.raise_for_status()

                data = response.json()
                result_ct = len(data.get(self.parse_key))
                if result_ct < 1:
                    break

                skip += limit
                yield from data.get(self.parse_key, data)

                self.logger.debug(f"Incrementing {skip} next items.")

    def fetch(self):
        return self.fetch_iter()
