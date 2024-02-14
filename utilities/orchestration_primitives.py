import json
import logging
import shutil
import traceback
from abc import abstractmethod
from dataclasses import dataclass, asdict
from functools import partial
from multiprocessing import Pool, cpu_count
from pathlib import Path
from typing import Any, Optional, Callable
from uuid import uuid4

from utilities.environment import get_secret


@dataclass
class SuccessMessage:
    job_id: Any
    environment: str
    service_name: str
    job_metadata: dict
    output_summary_location: str
    status: str = "success"


@dataclass
class JobParams:
    job_id: str

    @staticmethod
    @abstractmethod
    def _validate_params(param_dict: dict):
        """Validate proposed job parameters

        :param param_dict (dict): dictionary of job parameters (from job message)
        :raises NotImplementedError: Must be defined in child class
        """
        raise NotImplementedError("This must be defined in a child class.")

    @classmethod
    def from_param_dict(cls, param_dict: dict) -> "JobParams":
        """Define parameters for a job.

        :param Dict[str, str] param_dict: Desired parameters for job
        :raises Exception: If job_id, platform, or datatype field is missing from job definition.
        :return JobParams: Parameters for the job formatted as a JobParams object
        """
        cls._validate_params(param_dict)
        return JobParams(**param_dict)


class Infrastructure:

    def _download(self, *args, **kwargs):
        """
        Istructure-specific download method.

        :raises NotImplementedError: If called directly as this needs to be
        overriden in subclasses.
        """

        raise NotImplementedError("Must be defined in child class.")

    def download(
        self,
        origin: str,
        filenames: list[str],
        local_dir: Path,
        okay_if_exists=True,
    ):
        """Downloads files locally.

        :param str origin: Key/file prefix
        :param list[str] filenames: Filenames to download
        :param Path local_dir: Local directory to download to
        :param bool okay_if_exists: Whether we don't need to redownload if the file
        already exists locally, defaults to True
        """

        download_files = []
        for filename in filenames:
            download_name = str(local_dir / filename)
            if not Path(download_name).exists() or not okay_if_exists:
                download_files.append(filename)

        self._download(origin, download_files, local_dir)

    def upload(self, dest: str, output: list[Path], local_dir: Path = None):
        """Uploads local files to destination.

        :param str dest: Destination filepath prefix
        :param list[Path] output: Filenames to upload
        :param Optional[Path] local_dir: Local directory to find files for upload,
        defaults to None
        :raises NotImplementedError: If called directly as this needs to be
        overriden in subclasses.
        """
        raise NotImplementedError

    def connect_to_queue(self, queue_name: str):
        """Connect to desired queue.

        :param str queue_name: Name of queue to connect to
        :raises NotImplementedError: If called directly as this needs to be
        overriden in subclasses.
        """
        raise NotImplementedError

    def listen(self, callback: Callable[[dict[str, Any]], None]):
        """Listen to queue and do stuff if a message shows up.

        :param callable[[dict[str, Any]], None] callback: Function to call back to
        if a message shows up on queue.
        :raises NotImplementedError: If called directly as this needs to be
        overriden in subclasses.
        """
        raise NotImplementedError

    def enqueue_message(self, queue_name: str, message: str) -> None:
        """Takes a queue-name and properly formatted JSON string and sends it on
        the named queue.
        :param queue_name string name of queue
        :param message string JSON of message contents to be put on the queue
        :return None, action is enqueueing on external queue"""

        raise NotImplementedError


class Job:
    def __init__(
        self,
        params: JobParams,
        input_dir: Path = None,
        output_dir: Path = None,
        logger: logging.Logger = None,
        live: bool = False,
    ):
        self.params = params
        self.live = live
        self.output_dir = output_dir or self._generate_output_dir()
        self.input_dir = input_dir or Path()
        self.validate_dirs()
        self.logger = logger or logging.getLogger(__name__)

    def validate_dirs(self, to_check: list = None, make_live: list = None):
        to_check = to_check or [self.input_dir]
        make_live = make_live or [self.output_dir]
        if self.live:
            for dir in make_live:
                dir.mkdir(parents=True, exist_ok=True)
                to_check.append(dir)
        if missing := [x for x in to_check if not x.exists()]:
            raise FileNotFoundError(
                f"One or more required directories is missing for mapping job: {missing}"
            )

    def _generate_output_dir(self) -> Path:
        """Makes temporary local directory for use by this job alone.

        :return Path: Path of the newly created local directory, formatted as "tmp/<job_id>"
        """

        output_dir = Path(f"tmp/{self.params.job_id}")
        output_dir.mkdir(exist_ok=True, parents=True)
        return output_dir

    def manage_pool(self, func: callable, input_list: list, func_args: dict = {}):
        # create Pool
        pool = Pool(processes=cpu_count())
        self.logger.info(f"Created a pool with {cpu_count()} processes.")
        partial_func = partial(func, **func_args)
        results = pool.map(partial_func, input_list)
        pool.close()
        pool.join()

        return results

    @abstractmethod
    def do(self):
        """This has a deceptively simple name: it serves as the abstract
        function template to orchestrate/conduct all relevant business logic.

        :raises NotImplementedError: If called directly as this needs to be
        overriden in subclasses
        """

        raise NotImplementedError


class Worker:
    def __init__(self, infra_class: Any, job_queue_name: str, trigger: bool = True):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.istructure = infra_class(trigger=trigger)
        self.istructure.connect_to_queue(job_queue_name)
        if trigger:
            self.trigger()

    def trigger(self):
        """Triggers the worker to listen to messages on the relevant job queue."""
        self.logger.info(f"{self.__class__.__name__} is listening.")
        self.istructure.listen(callback=self.process)

    def upload(self, dest: str, output: list[Path], local_dir: Optional[Path] = None):
        """Uploads local files to destination .

        :param str dest: Destination filepath prefix
        :param list[Path] output: Filenames to upload
        :param Optional[Path] local_dir: Local directory to find files for upload,
        defaults to f"tmp/{dest}"
        """

        return self.istructure.upload(dest, output, local_dir)

    def cleanup(self, data_dir: Path):
        """Deletes specified directory.

        :param Path data_dir: Directory to delete
        """
        shutil.rmtree(data_dir)

    @staticmethod
    def _make_job_id():
        """Overridable method for creating a Job ID if none exists for an incoming
        message. Defaults to uuid4()."""
        return uuid4()

    def process(self, process_details: dict[str, Any]) -> bool:
        """Process the messages - turning them into job requirements and doing the job.
        If no job ID is provided in the message, this will create an ID for it.
        Deliver the result at the end."""

        job_id = process_details.get("job_id", self._make_job_id())
        process_details["job_id"] = job_id
        temp_dir = Path(f"tmp/{job_id}")
        temp_dir.mkdir(exist_ok=True, parents=True)
        job_kwarg_list = process_details.get("jobs", [])
        try:
            self.logger.info(f"Number of jobs for {job_id}: {len(job_kwarg_list)}")
            for job_kwargs in job_kwarg_list:
                self.do_job(job_id=job_id, job_kwargs=job_kwargs, data_dir=temp_dir)

            process_details["data_dir"] = str(temp_dir)
            return self.deliver(process_details)
        except Exception as e:
            tb = traceback.format_exc()
            self.logger.error(tb)
            raise e
        finally:
            self.cleanup(temp_dir)

    @abstractmethod
    def do_job(self, job_id: Any, job_kwargs: dict[str, Any], data_dir: Path):
        """Runs a job with the desired specifications.

        :param Any job_id: ID of job to execute
        :param dict[str, Any] job_kwargs: Arguments to pass to job object
        :param Path data_dir: Path to temp directory for use by this job alone.
        :raises NotImplementedError: If called directly as this needs to be
        overriden in subclasses.
        """
        raise NotImplementedError

    def deliver(self, process_details: dict[str, Any]) -> bool:
        """Enqueue the results at the end of the job."""
        job_id = process_details["job_id"]
        self.logger.info(f"Process completed for job {job_id}")
        # the fact this didn't error out before means yay success
        success_msg = SuccessMessage(
            job_id=job_id,
            environment=get_secret(secret_name="ENVIRONMENT"),
            service_name=self.__class__.__name__,
            output_summary_location=process_details["data_dir"],
            job_metadata=process_details["jobs"],
        )
        try:
            self.istructure.enqueue_message(
                get_secret("OUTPUT_QUEUE"), json.dumps(asdict(success_msg))
            )
            return True
        except Exception:
            self.logger.exception("Failed to deliver message.")
            return False
