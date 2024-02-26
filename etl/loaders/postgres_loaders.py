from ...utilities.etl_primitives import Loader
from ...utilities.environment import get_secret
import psycopg2 as pg
from datetime import datetime, timezone
from typing import Any, Iterator, Optional


DB_HOST = get_secret("DB_HOST")
DB_NAME = get_secret("DB_NAME")
DB_USER = get_secret("DB_USER")
DB_PW = get_secret("DB_PW")


class PGLoader(Loader):

    def __init__(self) -> None:
        super().__init__()

    def get_db_conn(self, autocommit: bool = True) -> pg.extensions.connection:
        self.logger.debug(f"Attempting connection to {DB_HOST}")
        conn = pg.connect(host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PW)

        conn.autocommit = autocommit
        return conn

    def make_temp_table(
        self,
        table_name: str,
        fields: list[str],
        cursor: Optional[pg.extensions.cursor] = None,
    ):

        if not cursor:
            connection = self.get_db_conn()
            cursor = connection.cursor()

        # TODO: add fieldset backoff to all fields in target table

        current_time = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S%f")
        temp_table_name = f"{table_name}_temp_{current_time}"
        fieldset = ", ".join(fields)
        create_query = f"""
            CREATE TEMP TABLE {temp_table_name} AS (
            SELECT {fieldset} FROM {table_name} LIMIT 1
            );
        """
        cursor.execute(create_query)
        return temp_table_name

    def upsert_temp_main(
        self, cursor, temp_table_name: str, table_name: str, fields: list[str]
    ):
        # TODO: allow customization of excluded fields
        update_fields = [
            x for x in fields if x.lower() != "id" and x.lower() != "created_at"
        ]
        old_fields = ",".join(update_fields)
        new_fields = ",".join([f"EXCLUDED.{field}" for field in update_fields])
        upsert_query = f"""
            INSERT INTO {table_name} SELECT DISTINCT * FROM {temp_table_name}
            ON CONFLICT (id) DO UPDATE SET ({old_fields}) = ({new_fields});
        """
        cursor.execute(upsert_query)


class PGStreamLoader(PGLoader):

    def __init__(self) -> None:
        super().__init__()

    def copy_string_iterator(
        self,
        items: Iterator[dict[str, Any]],
        table_name: str,
        fields: list[str],
        connection: Optional[pg.extensions.connection] = None,
    ) -> None:
        if not connection:
            connection = self.get_db_conn()
        self.logger.debug(f"Connected via {connection}")
        with connection.cursor() as cursor:
            temp_table_name = self.make_temp_table(
                table_name=table_name, cursor=cursor, fields=fields
            )
            cursor.copy_from(items, temp_table_name, sep="`", columns=fields)
            self.upsert_temp_main(
                cursor=cursor,
                temp_table_name=temp_table_name,
                table_name=table_name,
                fields=fields,
            )

    def load(self, data: Iterator, table_name: str, fields: list[str]):
        self.logger.info(f"Loading data to {table_name} via COPY FROM")
        return self.copy_string_iterator(
            items=data, table_name=table_name, fields=fields
        )
