import json
import logging
import os
import socket
import yaml
from collections import ChainMap, Counter
import boto3
import ast

# from functools import partial
from pathlib import Path
from typing import Optional

logformat = "%(asctime)s : %(levelname)s : %(name)s : %(message)s"
logging.basicConfig(level=logging.DEBUG, format=logformat)


class SecretError(Exception):
    def __init__(self, secret_name: str):
        message = f"""No secret for {secret_name} in environment.
            Please check spellings and environmental availability."""
        super().__init__(message)


class SecretConflict(Exception):
    def __init__(self, secrets: list):
        message = f"Conflicting secrets for '{secrets}'"
        super().__init__(message)


def _populate_local_secrets() -> dict:
    # look for local "*secrets.*" file
    secrets_list = []
    # I would like to move towards using the secrets manager on AWS.
    # In the interest of swiftness the base path where the lambda should look
    # for this is hardcoded.
    # dir = Path.cwd()
    dir = Path(__file__).parent
    secret_files = [
        filename
        for filename in dir.rglob("*secrets.*")
        if "example" not in filename.name
    ]
    logging.debug(f"Secret files in {dir}: {secret_files}")
    for secret_file in secret_files:
        # open, read, append to total secrets
        s_s = secret_file.suffix
        if s_s == ".yaml" or s_s == ".yml":
            load_op = yaml.safe_load_all
        elif s_s == ".json":
            load_op = json.load
        else:
            raise NotImplementedError(f"No read method known for {s_s}")
        with open(secret_file, "r") as fyle:
            data = load_op(fyle)
            if data.__class__.__name__ == "dict":
                secrets_list.append(data)
            elif data.__class__.__name__ == "list":
                secrets_list.extend(data)
            elif data.__class__.__name__ == "generator":
                # TODO: recursively unpack until first level of dicts;
                # currently v lazy
                data = [item for item in data]
                if isinstance(data[0], list):
                    data = [item for innerlist in data for item in innerlist]
                secrets_list.extend(data)
            else:
                raise NotImplementedError(
                    f"Data from secrets file not a list, dict, or generator: {
                        type(data)
                        }"
                )
    # check for collisions across multiple secrets files
    all_secrets = [key for sdict in secrets_list for key in sdict]
    logging.debug(f"All secret names: {all_secrets}")
    key_counter = Counter(all_secrets)
    bad_secrets = [key for key in key_counter if key_counter[key] > 1]
    if bad_secrets:
        raise SecretConflict(secrets=bad_secrets)

    # unpack list of dicts into one dict
    # NOTE: this method will overwrite duplicate keys, hence the check above
    return dict(ChainMap(*secrets_list))


def read_secrets_manager(
        secret_name: str,
        region_name: str = "us-east-1"
) -> dict:
    """Grabs all the secrets and their values attached to a specific
    AWS Secrets Manager secret name. It's no secret that the other
    secret functions here are dreadful, and this strives to replace
    local config files.
    :param str secret_name: Name of secret (contains many secrets)
    :return str: The dict with all the vars
    """

    session = boto3.session.Session()
    client = session.client(
        service_name="secretsmanager", region_name=region_name
    )
    get_secret_value_response = client.get_secret_value(SecretId=secret_name)
    return ast.literal_eval(get_secret_value_response["SecretString"])


LOCALSECRETS = _populate_local_secrets()


def find_self() -> str:
    """Determines the current location of service.

    :return str: The container metadata URI if deployed with ECS, the hostname
    and IP address of machine where it's running otherwise
    """
    home = os.getenv("ECS_CONTAINER_METADATA_URI")
    if home is None:
        home_name = socket.gethostname()
        ip = socket.gethostbyname(home_name)
        home = f"{home_name}, {ip}"
    return home


def _prepend_svc_env(secret_name: str) -> str:
    """Prepends secret name with relevant service and environment info.

    :param str secret_name: Secret name to prepend
    :return str: Secret name with service name and environment prepended to it
    """

    environment_name = os.getenv("ENVIRONMENT")
    assert environment_name

    # TODO: This is fixed in a brittle way - it will HAVE TO BE CHANGED to be
    # more robust if we extend this toolset outside.
    service_name = "PLUMBINGBIRD"

    prepended_secret_key = f"{service_name}_{environment_name}_{secret_name}"

    return prepended_secret_key.upper()


def check_for_local_secret(secret_name: str) -> Optional[str]:
    # look for secret_name w or w/o prefix
    secret = LOCALSECRETS.get(secret_name) or LOCALSECRETS.get(
        _prepend_svc_env(secret_name=secret_name)
    )
    return secret


def get_secret(secret_name: str) -> str:
    """Gets secret value corresponding to either the specified name or
    the prepended name, whichever is available.

    :param str secret_name: Name of secret
    :raises AssertionError: If value doesn't exist for both secret name and
    prepended secret name.
    :return str: Value corresponding to the secret name or
    prepended secret name.
    """
    if secret_name.lower() == "environment" or secret_name.lower() == "env":
        secret_name = "ENVIRONMENT"
    from_env = os.getenv(secret_name)
    from_env_w_prefix = os.getenv(_prepend_svc_env(secret_name=secret_name))
    from_local = check_for_local_secret(secret_name)
    secret = from_env or from_env_w_prefix or from_local
    try:
        assert secret
    except AssertionError:
        raise SecretError(secret_name=secret_name)
    return secret
