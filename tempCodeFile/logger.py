import logging
import os

class LoggerManager:
    PRINT_LOG = False
    
    def __init__(self, log_dir: str = "logs", log_level=logging.DEBUG):
        self.log_dir = log_dir
        self.log_level = log_level
        os.makedirs(self.log_dir, exist_ok=True)

    def _get_formatter(self, include_name=False):
        if include_name:
            return logging.Formatter('[%(asctime)s] [%(name)s] %(levelname)s - %(message)s', datefmt='%H:%M:%S')
        return logging.Formatter('[%(asctime)s] %(levelname)s - %(message)s', datefmt='%H:%M:%S')

    def _file_handler(self, filename: str, formatter):
        path = os.path.join(self.log_dir, filename)
        handler = logging.FileHandler(path)
        handler.setFormatter(formatter)
        return handler

    def _stream_handler(self, formatter):
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        return handler

    def get_logger(self, name: str = None, include_console: bool = True, propagate: bool = True, master_log: bool = False):
        """
        - If `name` is None => root logger
        - If `master_log` is True => also logs to main.log
        """
        is_root = name is None
        logger = logging.getLogger() if is_root else logging.getLogger(name)
        logger.setLevel(self.log_level)
        logger.propagate = propagate
        
        formatter = self._get_formatter(include_name=not is_root)

        handlers_to_add = []

        # Check global PRINT_LOG toggle
        if include_console and LoggerManager.PRINT_LOG:
            handlers_to_add.append(self._stream_handler(formatter))

        log_filename = "root.log" if is_root else f"{name.lower()}.log"
        handlers_to_add.append(self._file_handler(log_filename, formatter))

        if master_log and not is_root:
            # Attach to master 'main.log'
            handlers_to_add.append(self._file_handler("main.log", formatter))

        for handler in handlers_to_add:
            # Prevent duplicates
            if not any(isinstance(h, type(handler)) and getattr(h, 'baseFilename', None) == handler.baseFilename for h in logger.handlers):
                logger.addHandler(handler)

        return logger
