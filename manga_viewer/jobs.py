from PySide6.QtCore import QRunnable


class Job(QRunnable):
    def __init__(self, operation, deliver):
        super().__init__()
        self.operation = operation
        self.deliver = deliver

    def run(self):
        try:
            result = self.operation()
        except Exception as error:
            self.deliver(None, str(error) or type(error).__name__)
        else:
            self.deliver(result, None)
