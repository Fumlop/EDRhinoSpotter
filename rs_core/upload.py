"""Bookmark upload to a team server: a daemon thread posts new and changed bookmarks. See docs/UPLOAD.md."""

import enum
import hashlib
import json
import os
import pathlib
import threading
import urllib.parse

from rs_core import atomic, database
from rs_core.logging import logger
import rs_api

try:
    import requests         # ships inside EDMC, with its own certificates
except ImportError:         # a bare interpreter without it
    requests = None

try:
    from config import config
except ImportError:         # running outside EDMC
    config = None


DEBUG = False

# Beside the db: %LOCALAPPDATA%/RhinoSpotter, $XDG_DATA_HOME/RhinoSpotter on Linux.
UPLOAD_DATA_FILEPATH = pathlib.Path(database.ROOT, 'upload_data.json')
UPLOAD_DATA_VERSION = 1

NEW_BOOKMARKS_CHECK_INTERVAL        = 8 if DEBUG else 60 * 5    # s between checks
UPLOAD_RETRY_WAIT                   = 5         # s between attempts
STOP_JOIN_TIMEOUT                   = 1         # s stop() waits; a request in flight ends on the daemon thread
UPLOAD_TIMEOUT                      = 20        # s per request
MAX_UPLOAD_ATTEMPTS                 = 3


class Status(enum.Enum):
    IDLE            = 0
    UPLOADING       = 2
    SHUTTING_DOWN   = 3


UPLOAD_ENABLED_KEY              = 'rhinospotter_uploading_enabled'
UPLOAD_INCLUDE_CMDR_NAME_KEY    = 'rhinospotter_upload_cmdr_name'
UPLOAD_URL_KEY                  = 'rhinospotter_upload_url'
UPLOAD_ACCESS_KEY_KEY           = 'rhinospotter_upload_access_key'

# Hosts allowed over http; every other URL must be https (the access key is in the body).
LOOPBACK_HOSTS = ('localhost', '127.0.0.1', '::1')

# rs_api.bookmarks() keys whose change sends a bookmark again.
BOOKMARK_CHECKSUM_FIELDS = [
    'system',
    'body',
    'material',
    'location',
    'latitude',
    'longitude',
    'rigs',
    'density',
    'amount',
    'depleted',
    'depleted_at',
    'marked_at',
]


class UploadError(IOError):
    """A failed upload; str() is the panel line, saying what to do."""


class UploadCore():
    """Worker thread and upload state. Uploads only while `enabled`; main sets it from UPLOAD_ENABLED_KEY."""

    def __init__(self, enabled=False):
        self.enabled = enabled
        self.status = Status.IDLE
        self.status_msg = ''            # the panel's upload line, read by main._poll_landed

        self._uploaded_bookmarks_checksums = {}     # _get_bookmark_dict_key -> checksum of the last upload
        self._upload_thread = None
        self._stop = threading.Event()

        self._load_upload_data()

    def _load_upload_data(self) -> None:
        """Checksums from UPLOAD_DATA_FILEPATH; empty when it is missing, unreadable or not a JSON object.

        Never raises: main.start() builds UploadCore with uploads off too.
        """
        self._uploaded_bookmarks_checksums = {}
        if not UPLOAD_DATA_FILEPATH.exists():
            return
        try:
            with open(UPLOAD_DATA_FILEPATH, 'r', encoding='utf-8') as in_file:
                data = json.load(in_file)
            checksums = data.get('uploaded_bookmark_checksums', {})
            if not isinstance(checksums, dict):
                raise ValueError('uploaded_bookmark_checksums is not an object')
        except (OSError, ValueError, AttributeError) as exc:
            logger.error(f'Upload: upload_data.json unreadable, starting empty: {exc!r}')
            return
        self._uploaded_bookmarks_checksums = checksums

    def _save_upload_data(self) -> None:
        """Checksums to UPLOAD_DATA_FILEPATH."""
        data = {
            'version': UPLOAD_DATA_VERSION,
            'uploaded_bookmark_checksums': self._uploaded_bookmarks_checksums,
        }
        os.makedirs(UPLOAD_DATA_FILEPATH.parent, exist_ok=True)
        # Temp file + replace: a kill mid-write leaves the old file, not half a new one.
        atomic.write_text(str(UPLOAD_DATA_FILEPATH), json.dumps(data, indent=4))

    def _get_bookmark_checksum(self, bookmark) -> str:
        """MD5 hex of the BOOKMARK_CHECKSUM_FIELDS values, in that order."""
        md5 = hashlib.md5()
        for field_name in BOOKMARK_CHECKSUM_FIELDS:
            md5.update(str(bookmark[field_name]).encode('utf-8'))
        return md5.hexdigest()

    def _get_bookmark_dict_key(self, bookmark) -> str:
        """'<system>, <body without the system prefix> (<lat>, <lon>)'."""
        body_name = bookmark['body'][len(bookmark['system'])+1:]
        return f"{bookmark['system']}, {body_name} ({bookmark['latitude']}, {bookmark['longitude']})"

    def _get_new_bookmarks(self) -> list:
        """rs_api.bookmarks() not uploaded yet, or changed since their last upload."""
        bookmarks = []
        for bookmark in rs_api.bookmarks():
            key = self._get_bookmark_dict_key(bookmark)
            if self._uploaded_bookmarks_checksums.get(key) != self._get_bookmark_checksum(bookmark):
                bookmarks.append(bookmark)
        return bookmarks

    def _send_to_server(self, data) -> None:
        """One POST of `data`; on 200 their checksums are recorded.

        Raises UploadError with the panel line, or requests' ConnectionError / Timeout.
        """
        if not data:
            return

        upload_url = config.get_str(UPLOAD_URL_KEY, default='')
        access_key = config.get_str(UPLOAD_ACCESS_KEY_KEY, default='')

        if not upload_url:
            logger.error('Upload: no URL set')
            raise UploadError('Set the upload server URL in Settings')

        json_data = {
            'access_key':   access_key,
            'deposits':     data,
        }

        host = urllib.parse.urlsplit(upload_url).hostname
        if not upload_url.lower().startswith('https://') and host not in LOOPBACK_HOSTS:
            logger.error('Upload: URL is not https, not sent')
            raise UploadError('Upload server URL must start with https:// - fix it in Settings')

        # Host only: path or query of the URL can carry a token.
        logger.info(f'Upload: POST to {host}')
        response = requests.post(upload_url, json=json_data, timeout=UPLOAD_TIMEOUT)
        logger.info(f'Upload: Response = {response.status_code} {response}')

        if response.status_code == 200:
            for bookmark in data:
                key = self._get_bookmark_dict_key(bookmark)
                self._uploaded_bookmarks_checksums[key] = self._get_bookmark_checksum(bookmark)
            logger.info(f'Bookmarks successfully uploaded: {len(data)}')
            return

        logger.error(f'Upload: HTTP {response.status_code} {response.text[:200]!r}')
        if response.status_code == 401:
            raise UploadError('Upload refused - check the access key in Settings')
        if response.status_code == 502:
            # Cloudflare Tunnel up, server behind it down.
            raise UploadError('Upload server offline - ask whoever runs it')
        raise UploadError('Upload server error - ask whoever runs it')

    def _upload(self, bookmarks) -> None:
        """Up to MAX_UPLOAD_ATTEMPTS tries on connect errors and timeouts, one on an UploadError; the next check tries again."""
        # Read on every upload: the setting can change while EDMC runs.
        if not config.get_bool(UPLOAD_INCLUDE_CMDR_NAME_KEY, default=False):
            for bookmark in bookmarks:
                bookmark['commander'] = 'anonymous'

        self.status = Status.UPLOADING
        self.status_msg = f'Uploading {len(bookmarks)} bookmarks...'

        for attempt in range(1, MAX_UPLOAD_ATTEMPTS + 1):
            try:
                self._send_to_server(bookmarks)
                self._save_upload_data()
                self.status = Status.IDLE
                self.status_msg = f'{len(bookmarks)} bookmarks uploaded'
                return
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
                msg = 'Upload server unreachable - check the URL in Settings'
                # Type only: the requests message repeats the URL path.
                logger.error(f'Upload attempt {attempt}/{MAX_UPLOAD_ATTEMPTS}: {type(exc).__name__}')
            except UploadError as exc:
                # The server's answer or the settings: a retry 5 s later gets the same.
                self.status_msg = str(exc)
                logger.error(f'Upload: {exc}; next try in {NEW_BOOKMARKS_CHECK_INTERVAL} s')
                self.status = Status.IDLE
                return
            except Exception as exc:
                msg = 'Upload failed - details in the EDMC log'
                logger.error(f'Upload attempt {attempt}/{MAX_UPLOAD_ATTEMPTS}: {exc!r}')
            self.status_msg = msg
            if attempt < MAX_UPLOAD_ATTEMPTS and self._stop.wait(UPLOAD_RETRY_WAIT):
                return

        # status_msg keeps the last attempt's line: it says what to fix.
        logger.error(f'Upload failed {MAX_UPLOAD_ATTEMPTS} times, next try in {NEW_BOOKMARKS_CHECK_INTERVAL} s')
        self.status = Status.IDLE

    def _upload_worker(self) -> None:
        """Every NEW_BOOKMARKS_CHECK_INTERVAL s while enabled: upload new or changed bookmarks."""
        logger.info('Starting _upload_worker...')
        while True:
            if self.enabled:
                try:
                    bookmarks = self._get_new_bookmarks()
                    if bookmarks:
                        logger.info(f'Uploading {len(bookmarks)} bookmarks...')
                        self._upload(bookmarks)
                except Exception as exc:
                    logger.error(f'Upload check failed: {exc!r}')
            if self._stop.wait(NEW_BOOKMARKS_CHECK_INTERVAL):
                return

    def start(self) -> None:
        """Start the daemon worker thread."""
        logger.info('Starting upload thread...')
        self._upload_thread = threading.Thread(target=self._upload_worker, name='RhinoSpotter upload thread')
        self._upload_thread.daemon = True
        self._upload_thread.start()

    def stop(self) -> None:
        """Signal the worker, wait up to STOP_JOIN_TIMEOUT s. Upload data is saved after each upload."""
        logger.info('Shutting down...')
        self.enabled = False
        self.status = Status.SHUTTING_DOWN
        self._stop.set()
        if self._upload_thread:
            self._upload_thread.join(STOP_JOIN_TIMEOUT)
            self._upload_thread = None
        logger.info('Done')
