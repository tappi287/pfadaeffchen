from PyQt5.QtCore import QThread, QObject, pyqtSignal

from modules.job import Job
from modules.setup_log import setup_logging
from modules.utils import MoveJobSceneFile

LOGGER = setup_logging(__name__)


class FileTransferWorker(QObject):
    finished = pyqtSignal(Job)

    def __init__(self, job: Job):
        super(FileTransferWorker, self).__init__()
        self.job = job

    def work(self):
        local_file_location = MoveJobSceneFile.move_scene_file_to_local_location(self.job.file)

        if local_file_location:
            self.job.local_file = local_file_location
            self.job.scene_file_is_local = True

        # Update job status to queued
        self.job.status = 1

        self.finished.emit(self.job)


class JobFileTransfer(QObject):
    def __init__(self, parent, finished_callback, job):
        """

        :param modules.gui_service_manager.ServiceManager parent:
        :param callable finished_callback:
        :param modules.job.Job job:
        """
        super(JobFileTransfer, self).__init__(parent)

        self.job = job

        self.work_thread = QThread()
        self.worker = FileTransferWorker(job)
        self.worker.moveToThread(self.work_thread)
        self.worker.finished.connect(finished_callback)

        self.work_thread.started.connect(self.worker.work)
        self.work_thread.finished.connect(self._finish_thread)

    def start(self):
        LOGGER.info('Starting Job file transfer thread')
        self.work_thread.start()

    def _finish_thread(self):
        LOGGER.info('Job file transfer finished. Deleting file transfer objects.')
        self.work_thread.deleteLater()
        self.deleteLater()
