
from ebml.schema import EBMLDocument, UnknownElement, CONTAINER, BINARY

import json
import os
import datetime

class EBMLData(object):

    def __init__(self, filename):
        self.mod_name, _, self.cls_name = 'ebml.schema.matroska.MatroskaDocument'.rpartition('.')
        try:
            self.doc_mod = __import__(self.mod_name, fromlist=[self.cls_name])
            self.doc_cls = getattr(self.doc_mod, self.cls_name)
        except ImportError:
            parser.error('unable to import module %s' % self.mod_name)
        except AttributeError:
            parser.error('unable to import class %s from %s' % (self.cls_name, self.mod_name))



        self.video_info = {}
        self.video_info['filename'] = filename
        self.video_info['total_size'] = os.stat(filename).st_size
        self.video_info['clusters'] = []

        self.doc = self.doc_cls(open(filename, 'rb'))

    def get_data(self):
        offset = 0
        for el in self.doc.roots:
            self.fill_video_info(el, offset, self.video_info)
            offset += el.size
        return self.video_info

    def get_full_info(self):
        self.max_count = -1
        return self.get_data()

    def get_first_cluster_timedelta(self):
        self.max_count = 4
        data = self.get_data()
        ms = data['clusters'][0]['timecode']
        return datetime.timedelta(microseconds=ms*1000)

    def get_first_cluster_timecode(self):
        td = self.get_first_cluster_timedelta()
        hours   = td.days * 24 + td.seconds / 3600
        minutes = (td.seconds % 3600) / 60
        seconds = td.seconds % 60
        microseconds = td.microseconds
        return "%.2d:%.2d:%.2d.%.2d" % (hours, minutes, seconds, microseconds)

    def get_first_cluster_seconds(self):
        td = self.get_first_cluster_timedelta()
        return (td.microseconds + (td.seconds + td.days * 24 * 3600) * 10**6) / 10.0**6

    def fill_video_info(self, element, offset, video_info):
        if element.name == 'Duration':
            video_info['duration'] = element.value

        if element.name == 'DisplayWidth':
            video_info['width'] = element.value

        if element.name == 'DisplayHeight':
            video_info['height'] = element.value

        if element.name == 'Cluster':
            video_info['clusters'].append({'offset': offset})

        if element.name == 'Timecode':
            video_info['clusters'][-1]['timecode'] = element.value

        if element.type == CONTAINER:
            i = 0
            for sub_el in element.value:
                self.fill_video_info(sub_el, offset + element.head_size, video_info)
                offset += sub_el.size
                if i == self.max_count:
                    break
                i += 1

