from django.core.files.storage import default_storage


class ObjectStorageError(Exception):
    pass


class ObjectStorage:
    def __init__(self, storage=None):
        self.storage = storage or default_storage

    def save(self, key, uploaded_file, expected_size):
        try:
            stored_key = self.storage.save(key, uploaded_file)
            if stored_key != key:
                self.storage.delete(stored_key)
                raise ObjectStorageError("Object storage changed the immutable object key.")
            if not self.storage.exists(key) or self.storage.size(key) != expected_size:
                self.storage.delete(key)
                raise ObjectStorageError("Object storage could not verify the uploaded object.")
        except ObjectStorageError:
            raise
        except Exception as error:
            raise ObjectStorageError("The file could not be stored.") from error

    def open(self, key):
        try:
            if not self.storage.exists(key):
                return None
            return self.storage.open(key, "rb")
        except Exception as error:
            raise ObjectStorageError("The stored file is unavailable.") from error

    def exists(self, key):
        try:
            return self.storage.exists(key)
        except Exception as error:
            raise ObjectStorageError("Object storage could not be checked.") from error

    def delete(self, key):
        try:
            self.storage.delete(key)
        except Exception as error:
            raise ObjectStorageError("The stored object could not be removed.") from error


def get_object_storage():
    return ObjectStorage()
