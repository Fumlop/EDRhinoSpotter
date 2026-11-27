"""
Main code for uploading bookmarks data to a shared "team" server. Optionally
configured in plugin settings/prefs.

vScourge
"""

import enum
import hashlib
import json
import os
import pathlib
import queue
import threading
import time

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
    

### CONSTANTS ###

DEBUG = False

UPLOAD_DATA_FILEPATH = pathlib.Path(pathlib.Path(os.getenv('LOCALAPPDATA')), r'EDRhinoSpotter\upload_data.json')
UPLOAD_DATA_VERSION = 1

if DEBUG:
    NEW_BOOKMARKS_CHECK_INTERVAL    = 8         # 8 seconds
    UPLOAD_MIN_TIME_BETWEEN_UPLOADS = 10        # 10 seconds
else:
    NEW_BOOKMARKS_CHECK_INTERVAL    = 60 * 5    # 5 minutes
    UPLOAD_MIN_TIME_BETWEEN_UPLOADS = 60 * 1    # 1 minute

UPLOAD_TIMEOUT                      = 20        # 20 seconds
MAX_UPLOAD_ATTEMPTS                 = 3

class Status(enum.Enum):
    IDLE            = 0
    UPLOAD_PENDING  = 1
    UPLOADING       = 2
    SHUTTING_DOWN   = 3
    NO_CREDS        = 4

UPLOAD_ENABLED_KEY              = 'rhinospotter_uploading_enabled'
UPLOAD_INCLUDE_CMDR_NAME_KEY    = 'rhinospotter_upload_cmdr_name'
UPLOAD_URL_KEY                  = 'rhinospotter_upload_url'
UPLOAD_ACCESS_KEY_KEY           = 'rhinospotter_upload_access_key'

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


### CLASSES ###

class UploadCore():
    """
    Manage data and process of uploading bookmarks to a shared team server.
    This will be disabled and do nothing if user has not opted-into uploads in the EDMC RhinoSpotter plugin settings.
    """
    def __init__(self, enabled=False):
        self.enabled = enabled
        self.status = Status.IDLE
        self.status_msg = ''

        self._fatal_error = False
        self._uploaded_bookmarks_checksums = { }
        self._last_new_bookmarks_check_time = 0
        self._last_upload_time = time.time()
        
        self._upload_thread = None
        self._upload_queue = queue.Queue()

        self._load_upload_data()
        
    # PRIVATE
    
    def _load_upload_data(self) -> None:
        """
        Load the JSON file containing data for bookmarks that have been uploaded already.
        """
        if not UPLOAD_DATA_FILEPATH.exists():
            # Make folder if needed
            os.makedirs(UPLOAD_DATA_FILEPATH.parent, exist_ok=True)
            
            self._uploaded_bookmarks_checksums.clear()
            return
        
        with open(UPLOAD_DATA_FILEPATH, 'r') as in_file:
            try:
                data = json.load(in_file)
            except json.decoder.JSONDecodeError as exc:
                logger.error('Failed to decode session data JSON file. Starting new one.')
                data = { }

        self._uploaded_bookmarks_checksums = data.get('uploaded_bookmark_checksums', { })
        

    def _save_upload_data(self) -> None:
        """
        Save data for bookmarks that have been uploaded already.
        """
        data = {
            'version': UPLOAD_DATA_VERSION,
            'uploaded_bookmark_checksums': self._uploaded_bookmarks_checksums,
        }
        
        with open(UPLOAD_DATA_FILEPATH, 'w') as out_file:
            json.dump(data, out_file, indent=4)
    

    def _get_bookmark_checksum(self, bookmark) -> str:
        """
        Create checksum string from specific fields in a bookmark. This is used to uniquely identify its
        state, so we don't upload the same data for a bookmark twice.
        """
        md5 = hashlib.md5()
        
        for field_name in BOOKMARK_CHECKSUM_FIELDS:
            md5.update(str(bookmark[field_name]).encode('utf-8'))
        
        checksum = md5.hexdigest()
        
        return checksum


    def _get_bookmark_dict_key(self, bookmark) -> str:
        """
        Generate the key string used in the uploaded bookmarks dictionary. This is used to separate the checksums
        by deposit body + location.
        """
        body_name = bookmark['body'][len(bookmark['system'])+1:]
        key = f"{bookmark['system']}, {body_name} ({bookmark['latitude']}, {bookmark['longitude']})"
        return key
        

    def _get_new_bookmarks(self) -> list:
        """
        Fetch all bookmarks from the RhinoSpotter API. Then filter it down to only those bookmarks that are new,
        or have a different checksum indicating something in their data has been updated/changed.
        """
        bookmarks = [ ]
        
        # Revision changed, so get new bookmarks
        for bookmark in rs_api.bookmarks():
            key = self._get_bookmark_dict_key(bookmark)
            checksum = self._get_bookmark_checksum(bookmark)
            
            uploaded_checksum = self._uploaded_bookmarks_checksums.get(key)
            
            if not uploaded_checksum or uploaded_checksum != checksum:
                # This is a new bookmark, or an existing one we've uploaded but its data has changed
                bookmarks.append(bookmark)
                
        return bookmarks
    
    
    def _send_to_server(self, data) -> None:
        """
        Send bookmarks' data to shared server. Raises errors when there's a problem.
        Uploaded bookmarks have their checksums stored, so they aren't uploaded again in the same state.
        """
        if not data:
            return

        upload_url = config.get_str(UPLOAD_URL_KEY, default='')
        access_key = config.get_str(UPLOAD_ACCESS_KEY_KEY, default='')
        
        if not upload_url:
            self.status_msg = f'Upload Server URL not found in Settings'
            logger.error(self.status_msg)
            raise IOError(self.status_msg)

        json_data = {
            'access_key':   access_key,
            'deposits':     data,
        }
        
        logger.info(f'Upload: Connecting to "{upload_url}"...')
        
        response = requests.post(
            upload_url,
            json=json_data,
            timeout=UPLOAD_TIMEOUT
        )

        logger.info(f'Upload: Response = {response.status_code} {response}')
        
        if response.status_code == 200:
            # Success!
            for bookmark in data:
                key = self._get_bookmark_dict_key(bookmark)
                checksum = self._get_bookmark_checksum(bookmark)
                self._uploaded_bookmarks_checksums[key] = checksum

            logger.info(f'Bookmarks successfully uploaded: {len(data)}')
            
        elif response.status_code == 502:
            # Cloudflare Tunnel is responding, but the DB server on the other side is not
            self.status_msg = f'Error 502: Server offline'
            logger.error(self.status_msg)
            response.raise_for_status()
        else:
            msg = response.json().get('detail')
            self.status_msg = f'Error {response.status_code} {msg}'
            logger.error(self.status_msg)
            response.raise_for_status()
            

    def _upload_worker(self) -> None:
        """
        Monitor the queue for bookmarks. 
        If it contains any, upload them. Will wait a bit, if the last upload was too recent.
        """
        logger.info('Starting _upload_worker...')
        
        while True:
            if self._fatal_error:
                # Do nothing until EDMC is restarted
                break
            
            time.sleep(0.01)    # yeild to main thread

            if self.status == Status.SHUTTING_DOWN:
                return

            if self._upload_queue.empty():
                # Nothing to upload
                continue

            # We have bookmarks to upload, but it may not be time yet
            self.status = Status.UPLOAD_PENDING

            # There's bookmarks in the queue, and it's time to upload them
            bookmarks = self._upload_queue.get()

            self.status_msg = f'Upload {len(bookmarks)} pending...'

            if time.time() < self._last_upload_time + UPLOAD_MIN_TIME_BETWEEN_UPLOADS:
                # Too soon. Put them back in queue for now
                self._upload_queue.put(bookmarks)
                continue
            
            # If CMDR name option is disabled, clear that value in the bookmarks data
            upload_cmdr_name = config.get_bool(UPLOAD_INCLUDE_CMDR_NAME_KEY, default=False)
            
            if not upload_cmdr_name:
                for bookmark in bookmarks:
                    bookmark['commander'] = 'anonymous'
            
            # Starting a new upload
            self.status = Status.UPLOADING
            self.status_msg = f'Uploading {len(bookmarks)} bookmarks...'

            attempt = 1
            success = False
            
            while attempt <= MAX_UPLOAD_ATTEMPTS:
                try:
                    self._send_to_server(bookmarks)
                    self.status_msg = f'{len(bookmarks)} bookmarks uploaded'
                    success = True
                    break
                except requests.exceptions.ConnectionError:
                    msg = f'Attempt {attempt}/{MAX_UPLOAD_ATTEMPTS}: Server connect failed'
                    logger.error(msg)
                    self.status_msg = msg
                    attempt += 1
                except Exception as exc:
                    if str(exc).startswith('401'):
                        msg = 'Invalid upload access key'
                    else:
                        msg = f'{exc}'
                        
                    logger.error(f'Upload attempt {attempt}/{MAX_UPLOAD_ATTEMPTS}: {msg}')
                    self.status_msg = msg
                    
                    attempt += 1
                    
                if attempt <= MAX_UPLOAD_ATTEMPTS:
                    # Wait a bit before retry
                    time.sleep(5)

            # Success or failure, we're idle or pending
            self._last_upload_time = time.time()
            
            if success:
                self._save_upload_data()
                self.status = Status.IDLE
                #self.status_msg = ''
            else:
                # Put these bookmarks back in the queue, to retry next time
                logger.error('Upload failed, disabling uploads until EDMC restart')
                self.status = Status.IDLE
                self.status_msg = f'Upload failed'
                self._upload_queue.put(bookmarks)
                self._fatal_error = True


    # PUBLIC

    def start(self) -> None:
        """
        Start the worker thread that watches for queued bookmarks to upload
        """
        logger.info('Starting upload thread...')
        self._upload_thread = threading.Thread(target=self._upload_worker, name='RhinoSpotter upload thread')
        self._upload_thread.daemon = True
        self._upload_thread.start()
        
        
    def stop(self) -> None:
        """
        Shut down the thread, queue, and save our upload data
        """
        logger.info('Shutting down...')

        self.enabled = False
        self.status = Status.SHUTTING_DOWN
        
        self._upload_queue.put(None)  # Still necessary to get `this.queue.get()` to unblock
        self._upload_thread.join()
        self._upload_thread = None
        
        self._save_upload_data()
        
        logger.info('Done')


    def upload_bookmarks(self) -> None:
        """
        This is the main function called from elsewhere, that checks a few conditions before checking for
        new bookmarks, and adding any to the queue to be uploaded.
        """
        self.enabled = config.get_bool(UPLOAD_ENABLED_KEY, default=False)

        if not self.enabled or self._fatal_error:
            return

        cur_time = time.time()
        
        if cur_time < self._last_new_bookmarks_check_time + NEW_BOOKMARKS_CHECK_INTERVAL:
            # Too soon
            return
            
        bookmarks = self._get_new_bookmarks()

        if bookmarks:
            logger.info(f'Queuing {len(bookmarks)} bookmarks for upload...')
            self._upload_queue.put(bookmarks)
            
        self._last_new_bookmarks_check_time = cur_time
