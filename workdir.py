import os

from front import Front
from blobrepo.repository import Repo
from common import *
from base64 import b64decode, b64encode
import bloblist
import settings
import time

if sys.version_info >= (2, 6):
    import json
else:
    import simplejson as json


class Workdir:
    def __init__(self, repoUrl, sessionName, revision, root):
        assert os.path.isabs(root), "Workdir path must be absolute. Was: " + root
        self.repoUrl = repoUrl
        self.sessionName = sessionName
        self.revision = revision
        self.root = root
        self.front = None
        self.md5cache = {}

    def write_metadata(self):
        workdir_path = self.root
        metadir = os.path.join(workdir_path, settings.metadir)        
        if not os.path.exists(metadir):
            os.mkdir(metadir)
        statusfile = os.path.join(workdir_path, settings.metadir, "info")
        with open(statusfile, "wb") as f:
            json.dump({'repo_path': self.repoUrl,
                       'session_name': self.sessionName,
                       'session_id': self.revision}, f, indent = 4)    

    def checkout(self, write_meta = True):
        assert os.path.exists(self.root) and os.path.isdir(self.root)
        front = self.get_front()
        if write_meta:
            self.write_metadata()
        for info in front.get_session_bloblist(self.revision):
            print info['filename']
            data = b64decode(front.get_blob_b64(info['md5sum']))
            assert data or info['size'] == 0
            filename = os.path.join(self.root, info['filename'])
            if not os.path.exists(os.path.dirname(filename)):
                os.makedirs(os.path.dirname(filename))
            with open(filename, "wb") as f:            
                f.write(data)

    def checkin(self, write_meta = True, base_session = None):
        front = self.get_front()
        assert os.path.exists(self.root)
        unchanged_files, new_files, modified_files, deleted_files, ignored_files = \
            self.get_changes()
        #print "Changes:", unchanged_files, new_files, modified_files, deleted_files, ignored_files
        front.create_session(base_session)

        check_in_tree(front, self.root)
        # for f in new_files:
        #     check_in_file(front, self.root, f)
        # for f in modified_files:
        #     check_in_file(front, self.root, f)
        ## here

        session_info = {}
        session_info["name"] = self.sessionName
        session_info["timestamp"] = int(time.time())
        session_info["date"] = time.ctime()
        self.revision = front.commit(session_info)
        if write_meta:
            self.write_metadata()
        return self.revision

    def get_front(self):
        if not self.front:
            self.front = Front(Repo(self.repoUrl))
        return self.front

    def exists_in_session(self, csum):
        """ Returns true if a file with the given checksum exists in the
            current session. """
        blobinfos = self.get_front().get_session_bloblist(self.revision)
        for info in blobinfos:
            if info['md5sum'] == csum:
                return True
        return False

    def exists_in_workdir(self, csum):
        """ Returns true if at least one file with the given checksum exists
            in the workdir. """
        tree = self.get_tree()
        for f in tree:
            if self.cached_md5sum(f) == csum:
                return True
        return False

    def get_blobinfo(self, relpath):
        """ Returns the info dictionary for the given path and the current
            session. The given file does not need to exist, the information is
            fetched from the repository"""
        blobinfos = self.get_front().get_session_bloblist(self.revision)
        for info in blobinfos:
            if info['filename'] == relpath:
                return info
        return None

    def cached_md5sum(self, relative_path):
        if relative_path in self.md5cache:
            return self.md5cache[relative_path]
        csum = md5sum_file(os.path.join(self.root, relative_path))
        self.md5cache[relative_path] = csum
        return self.md5cache[relative_path]

    def get_tree(self):
        """ Returns a simple list of all the files and directories in the
            workdir (except meta directories). """
        def visitor(out_list, dirname, names):
            if settings.metadir in names:
                names.remove(settings.metadir)
            for name in names:
                name = unicode(name, encoding="utf_8")
                fullpath = os.path.join(dirname, name)
                if not os.path.isdir(fullpath):
                    out_list.append(fullpath)
        all_files = []
        print "Walking", self.root
        os.path.walk(self.root, visitor, all_files)
        #remove_rootpath = lambda fn: my_relpath(fn, os.path.dirname(self.root))
        #remove_rootpath = lambda fn: my_relpath(fn, os.path.dirname(self.root))
        #relative_paths = map(remove_rootpath, all_files)
        return all_files

    def rel_to_abs(self, relpath):
        return os.path.join(self.root, relpath)

    def get_changes(self, skip_checksum = False):
        """ Compares the work dir with the checked out revision. Returns a
            tuple of four lists: unchanged files, new files, modified
            files, deleted files. By default, checksum is used to
            determine changed files. If skip_checksum is set to True,
            only file modification date is used to determine if a file
            has been changed. """
        assert not skip_checksum, "skip_checksum is not yet implemented"
        front = self.get_front()
        existing_files_list = self.get_tree()
        print "All existing files:", existing_files_list
        bloblist = []
        if self.revision != None:
            bloblist = front.get_session_bloblist(self.revision)
        unchanged_files, new_files, modified_files, deleted_files, ignored_files = [], [], [], [], []
        for info in bloblist:
            fname = info['filename']
            if fname in existing_files_list:
                existing_files_list.remove(fname)
                if self.cached_md5sum(info['filename']) == info['md5sum']:
                    unchanged_files.append(fname)
                else:
                    modified_files.append(fname)                    
            if not os.path.exists(fname):
                deleted_files.append(fname)
        for f in existing_files_list:
            if is_ignored(f):
                existing_files_list.remove(f)
                ignored_files.append(f)
        new_files.extend(existing_files_list)

        remove_rootpath = lambda fn: my_relpath(fn, self.root)
        unchanged_files = map(remove_rootpath, unchanged_files)
        new_files = map(remove_rootpath, new_files)
        modified_files = map(remove_rootpath, modified_files)
        deleted_files = map(remove_rootpath, deleted_files)
        ignored_files = map(remove_rootpath, ignored_files)
        if self.revision == None:
            assert not unchanged_files
            assert not modified_files
            assert not deleted_files
        return unchanged_files, new_files, modified_files, deleted_files, ignored_files

def is_ignored(dirname, entryname = None):
    if entryname == None:
        entryname = os.path.basename(dirname)
        dirname = os.path.dirname(dirname)
    if settings.metadir == entryname:
        return True
    full_path = os.path.join(dirname, entryname)
    if os.path.isdir(full_path):
        return False
    elif not os.path.isfile(full_path):
        return True
    elif os.path.islink(full_path):
        return True
    return False

def check_in_file(sessionwriter, root, path):
    print root, path
    blobinfo = bloblist.create_blobinfo(path, root)
    if sessionwriter.has_blob(blobinfo["md5sum"]):
        sessionwriter.add_existing(blobinfo)
    else:
        with open(path, "rb") as f:
            data = f.read()
        assert len(data) == blobinfo["size"]
        assert md5sum(data) == blobinfo["md5sum"]
        sessionwriter.add(b64encode(data), blobinfo)


def check_in_tree(sessionwriter, root):
    """ Walks the tree starting at root, and checks in all found files
    in the given session writer """

    if root != get_relative_path(root):
        print "Warning: stripping leading slashes from given path"
        
    tree = TreeWalker(root)
    for dirname, entryname in tree:
        if is_ignored(dirname, entryname):
            tree.skip_dir()
            continue
        full_path = os.path.join(dirname, entryname)
        if os.path.isdir(full_path):
            continue
        check_in_file(sessionwriter, root, full_path)
        