import logging
from pathlib import Path

from utilities.orchestration_primitives import Job, JobParams
from utilities.environment import get_secret
from aws.utilities import get_client


class AWSJob(Job):
    def __init__(
        self,
        params: JobParams,
        input_dir: Path = None,
        output_dir: Path = None,
        logger: logging.Logger = None,
        live: bool = False,
    ):
        super().__init__(
            params=params,
            input_dir=input_dir,
            output_dir=output_dir,
            logger=logger,
            live=live,
        )

    def upload(self, dest: str, output: list[Path], local_dir: Path = None):
        """Uploads local files to S3.

        :param str dest: Destination filepath prefix
        :param List[Path] output: Filenames to upload
        :param Optional[Path] local_dir: Local directory to find files
        for upload, defaults to f"tmp/{dest}"
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
                    get_client(client_type="s3").upload_file(
                        Filename=str(path), Bucket=output_bucket, Key=dest_name
                    )
                except Exception:
                    self.logger.exception("Error in upload")
