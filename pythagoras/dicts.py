import os
import pickle
from abc import *
from typing import Set, Any, Tuple, Union, Sequence
import boto3
from pythagoras.global_objects import *

import jsonpickle
import jsonpickle.ext.numpy as jsonpickle_numpy
import jsonpickle.ext.pandas as jsonpickle_pandas

jsonpickle_numpy.register_handlers()
jsonpickle_pandas.register_handlers()


SimpleDictKey = Union[ str, Sequence[str] ]
""" A value which can be used as a key for SimplePersistentDict. 

SimpleDictKey must be a string or a sequence of strings.
Thec characters within strings are restricted to allowed_key_chars set.
"""

class SimplePersistentDict(ABC):
    """Dict-like class that only accepts keys which are sequences of strings (SimpleDictKey-s).

    An abstract base class for key-value stores. It accepts keys in a form of
    either a single sting or a sequence (tuple, list) of strings.
    It imposes no restrictions on types of values in the key-value pairs.

    The API for the class resembles the API of Python's built-in Dict.
    """

    def _normalize_key(self, key:SimpleDictKey) -> Tuple[str,...]:
        """Check if a key meets requirements and return its standardized form.

        A key must be either a string or a sequence of non-empty strings.
        If it is a single string, it will be transformed into a tuple,
        consisting of this sole string.

        Each string in a sequence can contain only alphanumerical characters
        and characters from this list: ()_-.=
        """

        try:
            iter(key)
        except:
            raise KeyError(f"Key must be a string or a sequence of strings.")
        if isinstance(key, str):
            key = (key,)
        for s in key:
            assert isinstance(s,str), (
                    "Key must be a string or a sequence of strings.")
            assert len(set(s) - allowed_key_chars) == 0, (
                "Only the following chars are allowed in a key:"
                + str(allowed_key_chars))
            assert len(s), "Only non-empty strings are allowed in a key"
        return key


    @abstractmethod
    def __contains__(self, key:SimpleDictKey) -> bool:
        raise NotImplementedError


    @abstractmethod
    def __getitem__(self, key:SimpleDictKey) -> Any:
        raise NotImplementedError


    def __setitem__(self, key:SimpleDictKey, value:Any):
        if self.immutable_items: # TODO: change to exceptions
            assert key not in self, "Can't modify an immutable key-value pair"
        raise NotImplementedError


    def __delitem__(self, key:SimpleDictKey):
        if self.immutable_items: # TODO: change to exceptions
            assert False, "Can't delete an immutable key-value pair"
        raise NotImplementedError


    @abstractmethod
    def __len__(self) -> int:
        raise NotImplementedError


    @abstractmethod
    def _generic_iter(self, iter_type: str):
        assert iter_type in {"keys", "values", "items"}
        raise NotImplementedError


    def __iter__(self):
        return self._generic_iter("keys")


    def keys(self):
        return self._generic_iter("keys")


    def values(self):
        return self._generic_iter("values")


    def items(self):
        return self._generic_iter("items")


    def get(self, key:SimpleDictKey, default:Any=None):
        if key in self:
            return self[key]
        else:
            return default


    def setdefault(self, key:SimpleDictKey, default:Any=None):
        if key in self:
            return self[key]
        else:
            self[key] = default
            return default


    def pop(self, key:SimpleDictKey, default:Any):
        if key in self:
            result = self[key]
            del self[key]
            return result
        else:
            return default


    def popitem(self) -> Any:
        key = next(iter(self))
        result = self[key]
        del self[key]
        return result


    def __eq__(self, other) -> bool:
        try:
            if len(self) != len(other):
                return False
            for k in other.keys():
                if self[k] != other[k]:
                    return False
            return True
        except:
            return False


    def __ne__(self, other) -> bool:
        return not (self == other)


    def clear(self):
        for k in self.keys():
            del self[k]


    def safe_delete(self, key:SimpleDictKey):
        """ Delete an item from a dictionary without raising an exception if the item does not exist.

        This method is absent in the original dict API, it is added here
        to minimize network calls for (remote) persistent dictionaries.
        """

        if self.immutable_items: # TODO: change to exceptions
            assert False, "Can't delete an immutable key-value pair"

        try:
            self.__delitem__(key)
        except:
            pass




class FileDirDict(SimplePersistentDict):
    """ A persistent Dict that stores key-value pairs in local files.

    A new file is created for each key-value pair.
    A key is either a filename (without an extension),
    or a sequence of directory names that ends with a filename.
    A value can be any Python object, which is stored in a file.

    FileDirDict can store objects in binary files (as pickles)
    or in human-readable text files (using jsonpickles).
    """

    def __init__(self
                 , dir_name: str = "FileDirDict"
                 , file_type: str = "pkl"
                 , immutable_items:bool = False):
        """A constructor defines location of the store and file format to use.

        dir_name is a directory that will contain all the files in
        the FileDirDict. If the directory does not exist, it will be created.

        file_type can take one of two values: "pkl" or "json".
        It defines which file format will be used by FileDirDict
        to store values.
        """

        super().__init__(immutable_items = immutable_items)

        self.file_type = file_type

        assert file_type in {"json", "pkl"}, (
            "file_type must be either pkl or json")
        assert not os.path.isfile(dir_name)
        if not os.path.isdir(dir_name):
            os.mkdir(dir_name)
        assert os.path.isdir(dir_name)

        self.base_dir = os.path.abspath(dir_name)

    def __len__(self) -> int:
        num_files = 0
        for subdir_info in os.walk(self.base_dir):
            files = subdir_info[2]
            files = [f_name for f_name in files
                     if f_name.endswith(self.file_type)]
            num_files += len(files)
        return num_files

    def clear(self):

        assert not self.immutable_items, (
            "Can't clear a dict that contains immutable items")

        for subdir_info in os.walk(self.base_dir, topdown=False):
            (subdir_name, _, files) = subdir_info
            num_files = len(files)
            for f in files:
                if f.endswith(self.file_type):
                    os.remove(os.path.join(subdir_name, f))
            if (subdir_name != self.base_dir) and len(os.listdir(subdir_name)) == 0:
                os.rmdir(subdir_name)

    def _build_full_path(self, key:SimpleDictKey, create_subdirs:bool=False, is_file_path:bool = True):
        key = self._normalize_key(key)
        key = [self.base_dir] + list(key)
        dir_names = key[:-1] if is_file_path else key

        if create_subdirs:
            current_dir = dir_names[0]
            for dir_name in dir_names[1:]:
                new_dir = os.path.join(current_dir, dir_name)
                if not os.path.isdir(new_dir):
                    os.mkdir(new_dir)
                current_dir = new_dir

        if is_file_path:
            file_name = key[-1] + "." + self.file_type
            return os.path.join(*dir_names, file_name)
        else:
            return os.path.join(*dir_names)

    def get_subdict(self, key:SimpleDictKey):  # TODO: add this method to the entire hierarchy of persistent dict classes
        full_dir_path = self._build_full_path(key, create_subdirs = True, is_file_path = False)
        return FileDirDict(dir_name = full_dir_path, file_type=self.file_type)

    def _read_from_file(self, file_name: str):
        if self.file_type == "pkl":
            with open(file_name, 'rb') as f:
                result = pickle.load(f)
        elif self.file_type == "json":
            with open(file_name, 'r') as f:
                result = jsonpickle.loads(f.read())
        else:
            raise ValueError("file_type must be either pkl or json")
        return result

    def _save_to_file(self, file_name: str, value:Any):
        if self.file_type == "pkl":
            with open(file_name, 'wb') as f:
                pickle.dump(value, f)
        elif self.file_type == "json":
            with open(file_name, 'w') as f:
                f.write(jsonpickle.dumps(value, indent=4))
        else:
            raise ValueError("file_type must be either pkl or json")

    def __contains__(self, key:SimpleDictKey) -> bool:
        filename = self._build_full_path(key)
        return os.path.isfile(filename)

    def __getitem__(self, key:SimpleDictKey) -> Any:
        filename = self._build_full_path(key)
        if not os.path.isfile(filename):
            raise KeyError(f"File {filename} does not exist")
        result = self._read_from_file(filename)
        return result

    def __setitem__(self, key:SimpleDictKey, value:Any):
        filename = self._build_full_path(key, create_subdirs=True)
        if self.immutable_items:
            assert not os.path.exists(filename), (
                "Can't modify an immutable item")
        self._save_to_file(filename, value)

    def __delitem__(self, key:SimpleDictKey):
        assert not self.immutable_items, "Can't delete immutable items"
        filename = self._build_full_path(key)
        if not os.path.isfile(filename):
            raise KeyError(f"File {filename} does not exist")
        os.remove(filename)

    def _generic_iter(self, iter_type: str):
        assert iter_type in {"keys", "values", "items"}
        walk_results = os.walk(self.base_dir)
        ext_len = len(self.file_type) + 1

        def splitter(path: str):
            result = []
            if path == ".":
                return result
            while True:
                head, tail = os.path.split(path)
                result = [tail] + result
                path = head
                if len(head) == 0:
                    break
            return tuple(result)

        def step():
            for dir_name, _, files in walk_results:
                for f in files:
                    if f.endswith(self.file_type):
                        prefix_key = os.path.relpath(
                            dir_name, start=self.base_dir)

                        result_key = (*splitter(prefix_key), f[:-ext_len])

                        if iter_type == "keys":
                            yield result_key
                        elif iter_type == "values":
                            yield self[result_key]
                        else:
                            yield (result_key, self[result_key])

        return step()


class S3_Dict(SimplePersistentDict):
    """ A persistent Dict that stores key-value pairs as S3 objects.

        A new object is created for each key-value pair.
        A key is either an objectname (a 'filename' without an extension),
        or a sequence of folder names (object name prefixes) that ends
        with an objectname. A value can be any Python object,
        which is stored in an object.

        S3_Dict can store objects in binary objects (as pickles)
        or in human-readable texts objects (using jsonpickles).
        """


    def __init__(self, bucket_name:str
                 , region:str = None
                 , dir_name:str = "S3_Dict"
                 , file_type:str = "pkl"
                 , immutable_items:bool = False):
        """A constructor defines location of the store and object format to use.

        bucket_name and region define an S3 location of the storage
        that will contain all the objects in the S3_Dict.
        If the bucket does not exist, it will be created.

        dir_name is a local directory that will be used to store tmp files.

        file_type can take one of two values: "pkl" or "json".
        It defines which object format will be used by S3_Dict
        to store values.
        """

        super().__init__(immutable_items = immutable_items, digest_len = 0)

        self.file_type = file_type
        self.local_cache = FileDirDict(dir_name = dir_name, file_type = file_type)

        if region is None:
            self.s3_client = boto3.client('s3')
        else:
            self.s3_client = boto3.client('s3', region_name=region)

        self.bucket = self.s3_client.create_bucket(Bucket=bucket_name)
        self.bucket_name = bucket_name

    def _build_full_objectname(self, key:SimpleDictKey) -> str:
        key = self._normalize_key(key)
        objectname =  "/".join(key)+ "." + self.file_type
        return objectname

    def __contains__(self, key:SimpleDictKey) -> bool:
        if self.immutable_items:
            file_name = self.local_cache._build_full_path(
                key, create_subdirs=True)
            if os.path.exists(file_name):
                return True
        try:
            obj_name = self._build_full_objectname(key)
            self.s3_client.head_object(Bucket=self.bucket_name, Key=obj_name)
            return True
        except:
            return False

    def __getitem__(self, key:SimpleDictKey) -> Any:
        file_name = self.local_cache._build_full_path(key, create_subdirs=True)

        if self.immutable_items:
            try:
                result = self.local_cache._read_from_file(file_name)
                return result
            except:
                pass

        obj_name = self._build_full_objectname(key)
        self.s3_client.download_file(self.bucket_name, obj_name, file_name)
        result = self.local_cache._read_from_file(file_name)
        if not self.immutable_items:
            os.remove(file_name)

        return result

    def __setitem__(self, key:SimpleDictKey, value:Any):
        file_name = self.local_cache._build_full_path(key, create_subdirs=True)
        obj_name = self._build_full_objectname(key)

        if self.immutable_items:
            key_is_present = False
            if os.path.exists(file_name):
                key_is_present = True
            else:
                try:
                    self.s3_client.head_object(
                        Bucket=self.bucket_name, Key=obj_name)
                    key_is_present = True
                except:
                    key_is_present = False

            assert not key_is_present, "Can't modify an immutable item"

        self.local_cache._save_to_file(file_name, value)
        self.s3_client.upload_file(file_name, self.bucket_name, obj_name)
        if not self.immutable_items:
            os.remove(file_name)

    def __delitem__(self, key:SimpleDictKey):
        assert not self.immutable_items, "Can't delete an immutable item"
        obj_name = self._build_full_objectname(key)
        self.s3_client.delete_object(Bucket = self.bucket_name, Key = obj_name)
        file_name = self.local_cache._build_full_path(key)
        if os.path.isfile(file_name):
            os.remove(file_name)

    def __len__(self) -> int:
        num_files = 0
        suffix = "." + self.file_type

        paginator = self.s3_client.get_paginator("list_objects")
        page_iterator = paginator.paginate(Bucket=self.bucket_name)

        for page in page_iterator:
            if "Contents" in page:
                for key in page["Contents"]:
                    obj_name = key["Key"]
                    if obj_name.endswith(suffix):
                        num_files += 1

        return num_files

    def _generic_iter(self, iter_type: str):
        assert iter_type in {"keys", "values", "items"}
        suffix = "." + self.file_type

        ext_len = len(self.file_type) + 1

        def splitter(full_name: str):
            result = full_name.split(sep="/")
            result[-1] = result[-1][:-ext_len]
            return tuple(result)

        def step():
            paginator = self.s3_client.get_paginator("list_objects")
            page_iterator = paginator.paginate(Bucket=self.bucket_name)
            for page in page_iterator:
                if "Contents" in page:
                    for key in page["Contents"]:
                        obj_name = key["Key"]
                        if not obj_name.endswith(suffix):
                            continue
                        obj_key = splitter(obj_name)
                        if iter_type == "keys":
                            yield obj_key
                        elif iter_type == "values":
                            yield self[obj_key]
                        else:
                            yield (obj_key, self[obj_key])

        return step()


class ImmutableS3_LocallyCached_Dict(S3_Dict):
    """ A persistent Dict that stores immutable key-value pairs as S3 objects, and caches them locally.

        A new object is created for each key-value pair.
        A key is either an objectname (a 'filename' without an extension),
        or a sequence of folder names (object name prefixes) that ends
        with an objectname. A value can be any Python object,
        which is stored in an object.

        Once the key-value pair is created, it can't be deleted or changed.

        The key-value pairs are stored in S3 backed, and also cached locally as files.

        ImmutableS3_LocallyCached_Dict can store objects in binary objects (as pickles)
        or in human-readable texts objects (using jsonpickles).
        """


    def __init__(self, bucket_name: str, region: str = None, dir_name: str = "S3_Dict", file_type: str = "pkl"):
        """A constructor defines location of the store, local cache, and object format to use.

        bucket_name and region define an S3 location of the storage
        that will contain all the objects in the S3_Dict.
        If the bucket does not exist, it will be created.

        dir_name is a local directory that will be used to store cached files.

        file_type can take one of two values: "pkl" or "json".
        It defines which object format will be used by S3_Dict
        to store values.
        """

        super().__init__(bucket_name, region, dir_name, file_type)
        self._enforce_immutability = True
        """ _enforce_immutability only exists for testing purposes, its value should never be changed"""

    def __contains__(self, key:SimpleDictKey) -> bool:
        return self.local_cache.__contains__(key) or super().__contains__(key)

    def __getitem__(self, key:SimpleDictKey) -> Any:
        obj_name = self._build_full_objectname(key)
        file_name = self.local_cache._build_full_path(key, create_subdirs=True)
        try:
            if not os.path.isfile(file_name):
                self.s3_client.download_file(self.bucket_name, obj_name, file_name)
        except:
            raise KeyError(f"Object {file_name} does not exist or could not be accessed")
        result =  self.local_cache[key]
        return result

    def __setitem__(self, key:SimpleDictKey, value:Any):
        if self._enforce_immutability and self.__contains__(key):
            raise KeyError(f"Key {key} is already present in ImmutableS3_LocallyCached_Dict, value can't be changed.")
        obj_name = self._build_full_objectname(key)
        file_name = self.local_cache._build_full_path(key, create_subdirs=True)
        self.local_cache[key]=value
        self.s3_client.upload_file(file_name, self.bucket_name, obj_name)

    def __delitem__(self, key:SimpleDictKey):
        if self._enforce_immutability:
            raise KeyError(f"Can't delete {key}: operation is not allowed for immutable Dict.")
        else:
            super().__delitem__(key)
            if key in self.local_cache:
                del self.local_cache[key]
