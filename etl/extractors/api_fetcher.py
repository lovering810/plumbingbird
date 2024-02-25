import requests
from typing import Any, Iterator
from utilities.etl_primitives import Fetcher
from utilities.environment import get_secret


class APIFetcher(Fetcher):

    def __init__(
        self,
        endpoint: str,
        base_url: str = None,
        auth: dict = None,
    ) -> None:
        base_url = base_url or get_secret("BASE_URL")
        self.base_url = base_url
        self.endpoint = endpoint
        self.auth = auth
        super().__init__()

    def compose_url(self, *args, **kwargs):
        """
        Helper fn to assemble the URL for queries (as in cases when
        URL manipulation is used for pagination)

        raises: NotImplementedError if called on parent class
        """
        raise NotImplementedError("Must be defined in child class.")

    def connect(self) -> requests.Session:
        """
        Connect to API with basic auth if creds are supplied
        return: requests.Session
        """
        session = requests.Session()
        if self.auth:
            API_USER = self.auth["API_USER"]
            API_PW = self.auth["API_PW"]
            session.auth = (API_USER, API_PW)
        return session

    def fetch(self, *args, **kwargs):
        """
        Abstract functional interface for all child classes to do what they do.

        raises: NotImplementedError if called on base class.
        """
        raise NotImplementedError("Must be defined in child class.")


class APIStreamFetcher(APIFetcher):

    def __init__(self, endpoint: str, base_url: str = None, auth: dict = None) -> None:
        super().__init__(endpoint, base_url, auth)

    @staticmethod
    def stop_iter(parsed_response: Any):
        """
        Function to determine if the query loop should end.
        Default behavior is to identify when no more results of relevance
        are coming back (len(parsed_response) < 1)
        """
        return len(parsed_response) < 1

    def parse_response(self, response_json: dict) -> Any:
        """
        Parse JSON of response for whatever is relevant to this fetcher.
        Intended to be overridden in child classes by bizlogic.
        Parent class defaults to returning the entire response_json.
        """
        return response_json

    def fetch_iter(self, batch_size: int = 100) -> Iterator[dict[str, Any]]:
        """
        Pages through a JSON-returning API, applying self.parse_response()
        to each response and returning results as an Iterator.

        :param batch_size int: how many results to request per page, defaults to 100
        """

        session = self.connect()
        current_index = 0
        batch_size = 100
        while True:
            with session as sesh:
                # TODO: expand the customization of the request
                # include additional params as necessary, rather than URL
                # manipulation only.
                response = sesh.get(self.compose_url(batch_size, current_index))
                response.raise_for_status()

                data = response.json()
                parsed_results = self.parse_response(data)
                if self.stop_iter(parsed_results):
                    break

                current_index += batch_size
                yield from parsed_results

                self.logger.debug(f"Incrementing {current_index} next items.")

    def fetch(self):
        return self.fetch_iter()
