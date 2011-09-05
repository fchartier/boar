#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2011 Mats Ekberg
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import with_statement
import hashlib
import os
import sqlite3
from weakref import proxy
from common import *
import atexit

class blobs_sha256:
    def __init__(self, repo, datadir):
        # Use a proxy to avoid circular reference to the repo,
        # allowing this object to be garbed at shutdown and triggering
        # the __del__ function.
        self.repo = proxy(repo)
        assert os.path.exists(datadir)
        assert os.path.isdir(datadir)
        self.datadir = datadir
        self.conn = None
        self.__init_db()
        atexit.register(self.__sync)

    def __init_db(self):
        if self.conn:
            return
        try:
            self.conn = sqlite3.connect(os.path.join(self.datadir, "sha256cache"), check_same_thread = False)
            self.conn.execute("CREATE TABLE IF NOT EXISTS checksums (md5 char(32) PRIMARY KEY, sha256 char(64) NOT NULL)")
            self.conn.commit()
        except Exception, e:
            warn("Exception while initializing blobs_sha256 derived database - harmless but things may be slow\n")
            warn("The reason was: "+ str(e))
            self.__reset()

    def __set_result(self, md5, sha256):
        try:
            self.conn.execute("INSERT INTO checksums (md5, sha256) VALUES (?, ?)", (md5, sha256))
            # No commit here - too slow. Let's do it at exit instead
        except Exception, e:
            warn("Exception while writing to blobs_sha256 derived database - harmless but things may be slow\n")
            warn("The reason was: "+ str(e))
            self.__reset()


    def __get_result(self, md5):
        try:
            c = self.conn.cursor()
            c.execute("SELECT sha256 FROM checksums WHERE md5 = ?", (md5,))
            rows = c.fetchall()
            if rows:
                assert len(rows) == 1
                return rows[0][0]
        except:
            warn("Exception while reading from blobs_sha256 derived database - harmless but things may be slow\n")
            self.__reset()
        return None

    def verify(self):
        try:
            c = self.conn.cursor()
            c.execute("SELECT md5, sha256 FROM checksums")
            rows = c.fetchall()
            print "Sha256 cache verifying %s items" % len(rows)
            for row in rows:
                md5, sha256 = row
                fresh_sha256 = self.__generate_sha256(md5)
                if fresh_sha256 != sha256:
                    warn("Stored sha256 does not match calculated value")
                    return False
                notice("Stored sha256 for %s seems correct" % md5)

        except Exception, e:
            warn("Exception while verifying sha256 storage: "+str(e))
            self.__reset()
            return False
        return True

    def __reset(self):
        warn("Resetting sha256 cache.\n"+
             "This is harmless, but things may be slow while the cache repopulates")
        self.conn.close()
        self.conn = None
        self.__init_db()

    def __generate_sha256(self, blob):
        md5 = hashlib.md5()
        sha256 = hashlib.sha256()
        reader = self.repo.get_blob_reader(blob)
        assert reader
        while True:
            block = reader.read(2**16)
            if block == "":
                break
            sha256.update(block)
            md5.update(block)
        assert md5.hexdigest() == blob, "blob did not match expected checksum"
        return sha256.hexdigest()

    def get_sha256(self, blob):
        result = self.__get_result(blob)
        if result:
            return result
        result = self.__generate_sha256(blob)
        self.__set_result(blob, result)
        return result
        
    def __sync(self):
        if self.conn:
            self.conn.commit()
