#!/usr/bin/env python3

import ast
import botocore
import boto3
import logging
import pathlib
import json
import smart_open
from pathlib import Path
from typing import List, Union, Optional, Dict
from utilities.environment import get_secret

logger = logging.getLogger(__name__)


###### S3 RESOURCES
def _get_all_s3_keys(prefix: str, suffix: str, bucket: str, client: botocore.client):
    """
    params:
    - prefix: Start of filename pattern to match in s3 (after the bucket)
    - suffix: End of filename pattern to match in s3 (after the bucket)
    - bucket: S3 bucket with target contents
    - client: Initialized s3 client object
    """
    keys = []
    next_token = ""

    while next_token is not None:
        token_arg = {"ContinuationToken": next_token} if next_token else {}
        results = client.list_objects_v2(Bucket=bucket, Prefix=prefix, **token_arg)

        for i in results.get("Contents", []):
            k = i.get("Key", "")

            if k.endswith(suffix) and not k.endswith("/"):
                keys.append((k, i["LastModified"]))

        next_token = results.get("NextContinuationToken")

    return keys


def get_all_filenames_in_s3_dir(
    s3_client: botocore.client,
    bucket: str,
    prefix: str,
    suffix: str = "",
    full_filename_flag=False,
    logger: logging.Logger = logger,
) -> list:
    """From a bucket and directory-level prefix, return the filepaths for all items in the directory-level prefix.
    NB: This really will get them all, so if you don't want 30K items, use wisely.
    Intended for eventual use with retrieve_df_from_s3_csv.
    :param s3_client botocore.client: boto3 thing that lets you talk to s3
    :param bucket string: Name of bucket in s3
    :prefix: Start of filename pattern to match in s3 (after the bucket)
    :suffix: End of filename pattern to match in s3 (after the bucket)
    :param logger logging.Logger: logger to tell you what's going on. If not assigned, uses the utility default.
    :return list of tuples of (filekey, file_last_modified_at)"""
    # Adapted from https://stackoverflow.com/questions/31918960/boto3-to-download-all-files-from-a-s3-bucket/31929277

    keys = _get_all_s3_keys(
        prefix=prefix, suffix=suffix, bucket=bucket, client=s3_client
    )
    logger.info(
        f"Retrieved {len(keys)} key/date combos for bucket {bucket}, key {prefix}"
    )

    return (
        [
            (f"s3://{bucket}/{filename}", last_modified_date)
            for filename, last_modified_date in keys
        ]
        if full_filename_flag
        else keys
    )


def get_json_from_s3_as_dict(
    session: boto3.Session, path: Union[str, pathlib.Path]
) -> Dict:
    """Gets a json from S3 as a JSON.

    :param boto3.Session session:  The AWS session that will grant access to the bucket in question.
    :param Union[str, pathlib.Path] path: The "s3://bucket-name/{fname}.json" path to get data from.
    :return Dict: Dictionary representation of JSON file at given path.
    """

    with smart_open.open(
        path,
        "rb",
        transport_params={"client": get_client(client_type="s3", session=session)},
    ) as f:
        return json.load(f)


def upload_dir_to_s3(
    dest: str,
    output: List[Path],
    local_dir: Optional[Path] = None,
    output_bucket: Optional[str] = None,
):
    """Uploads local files to S3.

    :param str dest: Destination filepath prefix
    :param List[Path] output: Filenames to upload
    :param Optional[Path] local_dir: Local directory to find files for upload, defaults to f"tmp/{dest}"
    :param str output_bucket: Destination s3 bucket
    """
    if local_dir is None:
        local_dir = Path(f"tmp/{dest}")
    for path in output:
        if path.is_dir():
            path_children = [f for f in path.iterdir()]
            upload_dir_to_s3(
                dest=f"{dest}/{path.name}",
                output=path_children,
                local_dir=path,
                output_bucket=output_bucket,
            )
        else:
            if output_bucket is None:
                output_bucket = get_secret("OUTPUT_BUCKET")
            try:
                dest_name = f"{dest}/{path.name}"
                get_client(client_type="s3").upload_file(
                    Filename=str(path), Bucket=output_bucket, Key=dest_name
                )
            except Exception:
                logger.exception("Error in upload")


######## Session, Client, Role Management


def read_secrets_manager(secret_name: str, region_name: str = "us-east-1") -> dict:
    """Grabs all the secrets and their values attached to a specific
    AWS Secrets Manager secret name. It's no secret that the other
    secret functions here are dreadful, and this strives to replace
    local config files.
    :param str secret_name: Name of secret (contains many secrets)
    :return str: The dict with all the vars
    """

    session = boto3.session.Session()
    client = session.client(service_name="secretsmanager", region_name=region_name)
    get_secret_value_response = client.get_secret_value(SecretId=secret_name)
    return ast.literal_eval(get_secret_value_response["SecretString"])


def _get_simple_auth_kwargs() -> Dict[str, str]:
    return {
        "aws_access_key_id": get_secret(secret_name="AWS_ACCESS_KEY_ID"),
        "aws_secret_access_key": get_secret(secret_name="AWS_SECRET_ACCESS_KEY"),
        "region_name": get_secret(secret_name="REGION"),
    }


def make_aws_session(session_kwargs: Dict[str, str] = None) -> boto3.Session:
    """Make AWS session using environment credentials.


    :return boto3.Session: AWS session
    """
    session_kwargs = session_kwargs or _get_simple_auth_kwargs()
    return boto3.Session(**session_kwargs)


def _get_role_kwargs(role_secret: str) -> dict:
    role_secret = role_secret.upper()

    role_account = get_secret(secret_name=f"AWS_{role_secret}_ACCT")
    role_name = get_secret(secret_name=f"AWS_{role_secret}_ROLE_NAME")
    role_arn = f"arn:aws:iam::{role_account}:role/{role_name}"

    role_session = f"{role_secret}_session"
    simple_kwargs = _get_simple_auth_kwargs()
    sts_client = boto3.client("sts", **simple_kwargs)

    assumed_role_object = sts_client.assume_role(
        RoleArn=role_arn, RoleSessionName=role_session
    )
    credentials = assumed_role_object["Credentials"]

    return {
        "aws_access_key_id": credentials["AccessKeyId"],
        "aws_secret_access_key": credentials["SecretAccessKey"],
        "aws_session_token": credentials["SessionToken"],
        "region_name": simple_kwargs["region_name"],
    }


def get_client(
    client_type, session: boto3.Session = None, role_secret: str = None
) -> botocore.client:
    session = session or make_aws_session(
        session_kwargs=(
            _get_role_kwargs(role_secret=role_secret)
            if role_secret
            else _get_simple_auth_kwargs()
        )
    )

    return session.client(client_type)


######## DynamoDB Resources
def get_dynamodb_table(
    table_name: str = None, session: Optional[boto3.Session] = None
) -> boto3.resources.base.ServiceResource:
    """Retrieve DynamoDB table by name

    :param str table_name: name of table being sought - defaults to data_muncher_jobs_ENV
    :param Optional[boto3.Session] session: boto3.Session to use. Will create new if none passed.
    :return dynamodb table: AWS DynamoDB Table, defaulting to data_muncher_jobs_ENV
    """
    session = session or make_aws_session(
        session_kwargs=_get_role_kwargs(role_secret="dynamodb")
    )
    table_name = (
        table_name or f"data_muncher_jobs_{get_secret(secret_name='ENVIRONMENT')}"
    )
    return session.resource("dynamodb").Table(table_name)


def create_dynamo_db_records(
    new_records_list: list, table: boto3.resources.base.ServiceResource
) -> None:
    """

    Insert list of records into a dynamodb table.

    :param list new_records_list: list of records to insert
    :param str table_name: name of dynamodb table
    """

    with table.batch_writer() as batch:
        for new_record in new_records_list:
            batch.put_item(Item=new_record)
