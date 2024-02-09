import boto3
import json
import logging
import traceback

from pathlib import Path
from typing import Any

from utilities.orchestration_primitives import Infrastructure
from orchestration.aws.utilities import get_client, get_secret


class AWSInfrastructure(Infrastructure):
    def __init__(self, trigger: bool = True):
        self.exit = False
        self.s3_client = self.assign_client(trigger=trigger)
        self.logger = logging.getLogger(self.__class__.__name__)
        self.queue = None  # NOTE: this will be a queue object

    @staticmethod
    def assign_client(trigger: bool = True):
        if trigger:
            return get_client(client_type="s3")
        else:
            return None

    @staticmethod
    def _get_boto_resource(resource_type: str) -> boto3.resources.base.ServiceResource:
        """Gets desired AWS resource

        :param str resource_type: Desired type of resource
        :return ServiceResource: Retrieved AWS resource
        """
        region_name = get_secret(secret_name="REGION")
        access_key = get_secret(secret_name="AWS_ACCESS_KEY_ID")
        secret_access_key = get_secret(secret_name="AWS_SECRET_ACCESS_KEY")
        session = boto3.session.Session(
            aws_access_key_id=access_key, aws_secret_access_key=secret_access_key
        )
        return session.resource(resource_type, region_name=region_name)

    # cannot type annotate output because of boto3's design choices:
    #  https://stackoverflow.com/questions/43128637/type-function-doesnt-return-correct-result-for-a-boto3-sqs-object
    def connect_to_queue(self, queue_name: str):
        """Connect to desired SQS queue.

        :param str queue_name: Name of SQS queue to connect to
        """
        boto_resource = self._get_boto_resource("sqs")
        self.queue = boto_resource.get_queue_by_name(QueueName=queue_name)
        return True  # TODO Is this needed?

    def listen(self, callback: callable[[dict[str, Any]], None]):
        """Listens to SQS queue and does stuff if a message shows up.

        :param Callable[[dict[str, Any]], None] callback: Function to call back to
        if a message shows up on queue.
        """
        while self.exit is False:  # TODO: identify errors to break loop on
            msgs = self.queue.receive_messages(MaxNumberOfMessages=10)
            for msg in msgs:
                try:
                    process_details = json.loads(msg.body)
                    callback(process_details)
                except Exception:
                    tb = traceback.format_exc()
                    self.logger.error(f"Failed to process message: {msg}.")
                    self.logger.error(f"Traceback: {tb}")

    def enqueue_message(self, queue_name: str, message: str) -> None:
        """Sends a JSON message to the desired SQS queue.

        :param str queue_name: Name of queue
        :param str message: JSON of message contents to be put on the queue
        """

        boto_resource = self._get_boto_resource("sqs")
        queue = boto_resource.get_queue_by_name(QueueName=queue_name)
        queue.send_message(MessageBody=message)

    def download(self, origin: str, filenames: list[str], local_dir: Path):
        """Downloads files locally from S3

        :param str origin: Key/File prefix
        :param list[str] filenames: Filenames to download
        :param Path local_dir: Local directory to download to
        """
        ingest_bucket = get_secret(secret_name="MF_BUCKET")
        for filename in filenames:
            self.s3_client.download_file(
                Bucket=ingest_bucket,
                Key=f"{origin}/{filename}",
                Filename=f"{str(local_dir)}/{filename}",
            )

    def upload(self, dest: str, output: list[Path], local_dir: Path = None):
        """Uploads local files to S3.

        :param str dest: Destination filepath prefix
        :param list[Path] output: Filenames to upload
        :param Optional[Path] local_dir: Local directory to find files for upload,
        defaults to f"tmp/{dest}"
        """
        if local_dir is None:
            local_dir = Path(f"tmp/{dest}")
        for path in output:
            if path.is_dir():
                path_children = [f for f in path.iterdir()]
                self.upload(
                    dest=f"{dest}/{path.name}", output=path_children, local_dir=path
                )
            else:
                try:
                    dest_name = f"{dest}/{path.name}"
                    output_bucket = get_secret("OUTPUT_BUCKET")
                    self.s3_client.upload_file(
                        Filename=str(path), Bucket=output_bucket, Key=dest_name
                    )
                except Exception:
                    self.logger.error(f"upload: {traceback.format_exc()}")
