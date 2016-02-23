"""Module that contains the the chaser (producer) classes.

.. moduleauthor:: Thanos Vassilakis <thanosv@gmail.com>

"""

import argparse
import cPickle
import glob
import hashlib
import os
import pprint
import re
import sys
import time
from collections import namedtuple


class Producer(object):
    """Base producer class.

    """


SIG_SZ = 256


def slugify(value):
    """
    Convert spaces to hyphens.
    Remove characters that aren't alphanumerics, underscores, or hyphens.
    Convert to lowercase. Also strip leading and trailing whitespace.
    """
    value = re.sub('[^\w\s-]', '', value).strip().lower()
    return re.sub('[-\s]+', '-', value)


class Tailer(Producer):
    def __init__(self, source_pattern, verbose=False, follow=True, dryrun=False, backfill=True):
        self.args = namedtuple('Args', 'source_pattern', 'verbose', 'follow')
        self.args.source_pattern = source_pattern
        self.args.verbose = verbose
        self.args.follow = follow
        self.checkpoint_filename = self.make_checkpoint_filename(self.args.source_pattern)

    def handoff(self, file_tailed, checkpoint, record):
        if self.args.verbose:
            self.console(file_tailed, checkpoint, record)
        else:
            sys.stdout.write(record)
        return record

    @staticmethod
    def make_checkpoint_filename(source_pattern, path=None):
        if not path:
            path = os.path.join(os.path.expanduser("~"), '.tailchase')
        if not os.path.exists(path):
            os.makedirs(path)
        return os.path.join(path, os.path.basename(slugify(source_pattern) + '.checkpoint'))

    def should_tail(self, file_to_check, checkpoint):
        if self.args.verbose:
            self.console('should_tail', file_to_check, checkpoint)
        stat = os.stat(file_to_check)
        if self.args.verbose:
            self.console(stat)
        sig = self.make_sig(file_to_check, stat)
        if not checkpoint:
            if self.args.verbose:
                self.console('No Checkpoint')
            return file_to_check, (sig, stat.st_ctime, 0)
        if self.args.verbose:
            self.console('should_tail', file_to_check, checkpoint, sig == checkpoint[0])
        if sig == checkpoint[0] and checkpoint[2] < stat.st_size:
            retval = file_to_check, checkpoint
            if self.args.verbose:
                self.console('SIG the same', retval)
            return retval
        if stat.st_mtime > checkpoint[1]:
            if self.args.verbose:
                self.console(" Younger", file_to_check, (sig, stat.st_mtime, 0))
            return file_to_check, (sig, stat.st_mtime, 0)
        if self.args.verbose:
            self.console('skipping', file_to_check, (sig, stat.st_ctime, 0))

    @classmethod
    def make_sig(cls, file_to_check, stat):
        return hashlib.sha224(open(file_to_check).read(SIG_SZ)).hexdigest()

    def load_checkpoint(self, checkpoint_filename):
        try:
            if self.args.verbose:
                print 'loding'
            sig, mtime, offset = cPickle.load(open(checkpoint_filename))
            if self.args.verbose:
                self.console('loaded', checkpoint_filename, (sig, mtime, offset))
            return sig, mtime, offset
        except (IOError, EOFError, ValueError):
            return '', 0, 0

    def save_checkpoint(self, checkpoint_filename, checkpoint):
        if self.args.verbose:
            self.console('dumping', checkpoint_filename, checkpoint)
        return cPickle.dump(checkpoint, open(checkpoint_filename, 'wb'))

    def tail(self):
        checkpoint = self.load_checkpoint(self.checkpoint_filename)
        while True:
            try:
                to_tail = filter(None, sorted((self.should_tail(file_to_check, checkpoint)
                                               for file_to_check in glob.glob(self.args.source_pattern)),
                                              key=lambda x: x[1][1] if x else x))
                if not to_tail:
                    time.sleep(10)
                    continue
                if self.args.verbose:
                    pprint.pprint(to_tail)
                    self.console('checkpoint', checkpoint)
                if self.args.verbose:
                    self.console('to_tail', to_tail)
                if self.args.verbose:
                    time.sleep(5)
                file_to_tail, checkpoint = to_tail[0]
                to_tail = to_tail[1:]

                for offset, record in self.process(file_to_tail, checkpoint):
                    self.handoff(file_to_tail, checkpoint, record)
                    checkpoint = checkpoint[0], checkpoint[1], offset
                    self.save_checkpoint(self.checkpoint_filename, checkpoint)
                if not to_tail:
                    return
            except KeyboardInterrupt:
                return
            except:
                import traceback
                traceback.print_exc()
            finally:
                self.save_checkpoint(self.checkpoint_filename, checkpoint)
            time.sleep(5)

    def process(self, filename, (sig, st_mtime, offset)):
        with open(filename, 'rb') as file_to_tail:
            if self.args.verbose:
                self.console('offset', offset)
            # raw_input()
            file_to_tail.seek(offset, 0)
            if self.args.verbose:
                self.console(file_to_tail.tell())
            # raw_input()
            while True:
                record = self.read_record(file_to_tail)
                if not record:
                    break
                else:
                    yield file_to_tail.tell(), record

    def read_record(self, file_to_tail):
        return file_to_tail.readline()

    @classmethod
    def add_arguments(cls, parser=None):
        if not parser:
            parser = argparse.ArgumentParser(description='the ultimate tail chaser',
                                             prog='tailer',
                                             usage='%(prog)s [options] source_pattern'
                                             )
        parser.add_argument('source_pattern',
                            help='source pattern is the glob path to a file to be tailed plus its rotated versions')
        parser.add_argument('--verbose', action='store_true', default=False,
                            help='prints a lot crap, default is: %s' % False)
        parser.add_argument('--dryrun', action='store_true', default=False,
                            help='prints a lot crap and no hand-off, default is: %s' % False)
        parser.add_argument('--backfill', action='store_true', default=True,
                            help='backfill with rolled logs, default is: %s' % True)
        return parser

    @classmethod
    def cli(cls, argv=sys.argv):
        print argv
        arg_parse = cls.add_arguments()
        Tailer(**vars(arg_parse.parse_args(argv[1:]))).tail()

    @staticmethod
    def console(*args):
        print(args)


if __name__ == '__main__':
    Tailer.cli()
