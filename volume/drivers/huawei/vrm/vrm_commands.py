# vim: tabstop=4 shiftwidth=4 softtabstop=4

"""
[VRM DRIVER] VRM CLIENT.

"""
import json
import urlparse

from oslo.config import cfg
from cinder import exception as cinder_exception
from cinder.openstack.common import log as logging
from cinder.volume.drivers.huawei.vrm import exception as driver_exception
from cinder.openstack.common.gettextutils import _
from cinder.volume.drivers.huawei.vrm.conf import FC_DRIVER_CONF


try:
    from eventlet import sleep
except ImportError:
    from time import sleep

TASK_WAITING = 'waiting'
TASK_RUNNING = 'running'
TASK_SUCCESS = 'success'
TASK_FAILED = 'failed'
TASK_CANCELLING = 'cancelling'
TASK_UNKNOWN = 'unknown'

CONF = cfg.CONF


LOG = logging.getLogger(__name__)


class VRM_COMMANDS(object):
    USER_AGENT = 'VRM-HTTP-Client for OpenStack'
    RESOURCE_URI = 'uri'
    TASK_URI = 'taskUri'
    BASIC_URI = '/service'
    glanceServer_host = ''
    glanceServer_port = ''
    version = CONF.vrm_version
    site_uri = ''

    def __init__(self):
        self.site_urn = None
        self.site_uri = None

        glanceServer_Info = str(CONF.glance_api_servers).split(':')
        LOG.info("glance_api_servers is [%s]", CONF.glance_api_servers)
        LOG.info("sxmatch glanceServer_Info is %s", glanceServer_Info)
        self.glanceServer_host = glanceServer_Info[0] + ":" + glanceServer_Info[1]
        self.glanceServer_host = self.glanceServer_host.replace("['", '')
        LOG.info("sxmatch glanceServer_host is %s", self.glanceServer_host)
        self.glanceServer_port = glanceServer_Info[1].replace("']", '')
        LOG.info("sxmatch glanceServer_port is %s", self.glanceServer_port)

    """Generate command to be sent to VRM."""

    def _joined_params(self, params):
        param_str = []
        for k, v in params.items():
            if (k is None) or (v is None) or len(k) == 0:
                continue
            if k == 'scope' and v == self.site_urn:
                continue
            param_str.append("%s=%s" % (k, str(v)))
        return '&'.join(param_str)

    def _joined_body(self, params):
        param_str = []
        for k, v in params.items():
            if (type(k) is type(None)) or (type(v) is type(None)) or len(k) == 0:
                continue

            if type(v) in [int]:
                param_str.append('"%s":%s' % (k, str(v)))
            elif type(v) in [str, unicode]:
                param_str.append('"%s":"%s"' % (k, str(v)))
            elif type(v) in [bool]:
                param_str.append('"%s":%s' % (k, str(v).lower()))
            elif type(v) in [dict]:
                param_str1 = json.dumps(v)
                param_str.append('"%s":%s' % (k, param_str1))
            else:
                pass

        if len(param_str) > 0:
            return '{' + ','.join(param_str) + '}'
        else:
            return None


    def _combine_vmConfig(self, **kwargs):
        cpu_quantity = 1
        mem_quantityMB = 1024
        datastoreUrn = CONF.vrm_sm_datastoreurn
        disk_quantityGB = 10
        image_size = 10

        if image_size > disk_quantityGB:
            LOG.error(_("image is larger than sys-vol."))
            raise cinder_exception.ImageTooLarge

        cpu = {'quantity': cpu_quantity}
        memory = {'quantityMB': mem_quantityMB}
        disks = [
            {
                'datastoreUrn': datastoreUrn,
                'quantityGB': disk_quantityGB,
                'volType': 0,
                'sequenceNum': 1,
            }
        ]
        properties = {
            'isEnableHa': True,
            'reoverByHost': False,
            'isEnableFt': False
        }

        vmConfigBody = {
            'cpu': cpu,
            'memory': memory,
            'disks': disks,
            'properties': properties,
        }
        return vmConfigBody

    def _combine_os_options(self, **kwargs):
        osOptions = {
            'osType': 'Windows',
            'osVersion': 26
        }
        return osOptions

    def init_site(self, uri, urn):
        self.site_uri = uri
        self.site_urn = urn
        return

    def _generate_url(self, path, query=None, frag=None):
        LOG.info(_("[BRM-DRIVER] call _generate_url() "))
        if CONF.vrm_ssl:
            scheme = 'https'
        else:
            scheme = 'http'
        fc_ip = FC_DRIVER_CONF.fc_ip
        fc_image_path = FC_DRIVER_CONF.fc_image_path
        netloc = str(fc_ip) + ':' + str(CONF.vrm_port)
        if path.startswith(self.BASIC_URI):
            url = urlparse.urlunsplit((scheme, netloc, path, query, frag))
        else:
            url = urlparse.urlunsplit((scheme, netloc, self.BASIC_URI + str(path), query, frag))

        return url

    def generate_vrm_cmd(self, cmd, **kwargs):
        cpu = {'quantity': 1}
        memory = {'quantityMB': 1024}
        disks = {'datastoreUrn': 'urn:sites:4749082E:datastores:2', 'quantityGB': 10, 'volType': 1, 'isThin': True,
                 'sequenceNum': 1, }
        properties = {'isEnableHa': True, 'reoverByHost': False, 'isEnableFt': False}
        COMMANDS = {
            'v5.1': {
                'list_tasks': ('GET',
                               ('/tasks', kwargs.get(self.RESOURCE_URI), None, None),
                               {},
                               {},
                               False),
                'list_hosts': ('GET',
                               ('/hosts', kwargs.get(self.RESOURCE_URI), None, None),
                               {'limit': kwargs.get('limit'),
                                'offset': kwargs.get('offset'),
                                'scope': kwargs.get('scope')
                               },
                               {},
                               False),
                'list_datastores': ('GET',
                                    ('/datastores', kwargs.get(self.RESOURCE_URI), None, None),
                                    {'limit': kwargs.get('limit'),
                                     'offset': kwargs.get('offset'),
                                     'scope': kwargs.get('scope')
                                    },
                                    {},
                                    False),
                'list_volumes': ('GET',
                                 ('/volumes', kwargs.get(self.RESOURCE_URI), None, kwargs.get('id')),
                                 {'limit': kwargs.get('limit'),
                                  'offset': kwargs.get('offset'),
                                  'scope': kwargs.get('scope')
                                 },
                                 {},
                                 False),
                'create_volume': ('POST',
                                  ('/volumes', None, None, None),
                                  {},
                                  {'name': kwargs.get('name'),
                                   'quantityGB': kwargs.get('quantityGB'),
                                   'datastoreUrn': kwargs.get('datastoreUrn'),
                                   'uuid': kwargs.get('uuid'),
                                   'isThin': kwargs.get('isThin'),
                                   'type': kwargs.get('type'),
                                   'indepDisk': kwargs.get('indepDisk'),
                                   'persistentDisk': kwargs.get('persistentDisk'),
                                   'volumeId': kwargs.get('volumeId'),
                                  },
                                  True),
                'delete_volume': ('DELETE',
                                  ('/volumes', kwargs.get(self.RESOURCE_URI), None, None),
                                  {},
                                  {},
                                  True),

                'list_volumesnapshot': ('GET',
                                        ('/volumesnapshots', None, kwargs.get('uuid'), None),
                                        {'limit': kwargs.get('limit'),
                                         'offset': kwargs.get('offset'),
                                         'scope': kwargs.get('scope')
                                        },
                                        {},
                                        False),
                'create_volumesnapshot': ('POST',
                                          ('/volumesnapshots', None, None, None),
                                          {},
                                          {'volumeUrn': kwargs.get('vol_urn'), 'snapshotUuid': kwargs.get('uuid'),
                                          },
                                          False),
                'delete_volumesnapshot': ('DELETE',
                                          ('/volumesnapshots', None, None, kwargs.get('id')),
                                          {},
                                          {
                                              'snapshotUuid': kwargs.get('snapshotUuid'),
                                          },
                                          True),
                'createvolumefromsnapshot': ('POST',
                                             ('/volumesnapshots', None, "createvol", None),
                                             {},
                                             {'snapshotUuid': kwargs.get('uuid'),
                                              'volumeName': kwargs.get('name'),
                                             },
                                             True),
                'clone_volume': ('POST',
                                 ('/volumes', None, kwargs.get('src_name'), 'action/copyVol'),
                                 {},
                                 {'destinationVolumeID': kwargs.get('dest_name')
                                 },
                                 True),
                'copy_image_to_volume': ('POST',
                                         ('/volumes/imagetovolume', None, None, None),
                                         {},
                                         {
                                             'volumePara': {
                                                 'quantityGB': kwargs.get('volume_size'),
                                                 'urn': kwargs.get('volume_urn')
                                             },
                                             'imagePara': {
                                                 'id': kwargs.get('image_id'),
                                                 'url': kwargs.get('image_location')
                                             },
                                             'location': kwargs.get('host_urn'),
                                             'needCreateVolume': False
                                         },
                                         True),
                'copy_volume_to_image': ('POST',
                                         ('/volumes/volumetoimage', None, None, None),
                                         {},
                                         {
                                             'volumePara': {'urn': kwargs.get('volume_urn'),
                                                            'quantityGB': kwargs.get('volume_size')},
                                             'imagePara': {'id': kwargs.get('image_id'), 'url': kwargs.get('image_url')}
                                         },
                                         True),
                'import_vm_from_image': ('POST',
                                         ('/vms/action/import', None, None, None),
                                         {},
                                         dict({
                                             'name': 'name',
                                             'location': kwargs.get('host_urn'),
                                             'autoBoot': 'false',
                                             'url': kwargs.get('url'),
                                             'protocol': 'nfs',
                                             'vmConfig': {
                                                 'cpu': {
                                                     'quantity': 1
                                                 },
                                                 'memory': {
                                                     'quantityMB': 1024
                                                 },
                                                 'disks': [
                                                     {
                                                         'pciType': 'IDE',
                                                         'datastoreUrn': kwargs.get('ds_urn'),
                                                         'quantityGB': kwargs.get('vol_size'),
                                                         'volType': 0,
                                                         'sequenceNum': 1,
                                                     },
                                                 ],
                                             },
                                             'osOptions': {
                                                 'osType': 'Windows',
                                                 'osVersion': 32
                                             }
                                         }),
                                         True),
                'detach_vol_from_vm': ('POST',
                                       ('/vms', None, kwargs.get('vm_id'), 'action/detachvol'),
                                       {},
                                       {'volUrn': kwargs.get('volUrn')},
                                       True),
                'stop_vm': ('POST',
                            ('/vms', None, kwargs.get('vm_id'), 'action/stop'),
                            {},
                            {'mode': kwargs.get('mode')},
                            True),
                'delete_vm': ('DELETE',
                              ('/vms', None, kwargs.get('vm_id'), None),
                              {},
                              {},
                              True),
                'query_vm': ('GET',
                             ('/vms', None, kwargs.get('vm_id'), None),
                             {},
                             {},
                             False),
                'list_templates': ('GET',
                                   ('/vms', None, None, None),
                                   {'limit': kwargs.get('limit'),
                                    'offset': kwargs.get('offset'),
                                    'scope': kwargs.get('scope'),
                                    'isTemplate': 'true'
                                   },
                                   {},
                                   False),
                'clone_vm': ('POST',
                             ('/vms', None, kwargs.get('template_id'), 'action/clone'),
                             {},
                             dict({
                                 "name": "cinder-plugin-temp-vm",
                                 "description": "cinder-plugin-temp-vm",
                                 "isLinkClone": kwargs.get('linked_clone'),
                                 'location': kwargs.get('host_urn'),
                                 'autoBoot': 'false',

                                'vmConfig':
                                {
                                    'cpu':
                                    {
                                         'quantity': 2
                                    },
                                    'memory':
                                    {
                                        'quantityMB': 1024
                                    },
                                    'disks':
                                    [{
                                         'pciType': 'IDE',
                                         'datastoreUrn': kwargs.get('ds_urn'),
                                         'quantityGB': kwargs.get('volume_size'),
                                         'volType': 0,
                                         'sequenceNum': 1,
                                         'isThin': kwargs.get('is_thin')
                                    },],
                                 },
                             }),
                             True),
            },

            'v2.0': {}
        }

        path = query = body = None

        LOG.info("[BRM-DRIVER] version is [%s]", self.version)
        if self.version not in COMMANDS.keys():
            raise driver_exception.UnsupportedVersion()
        else:
            commands = COMMANDS[self.version]

        if cmd not in commands.keys():
            raise driver_exception.UnsupportedCommand()
        else:
            (method, pathparams, queryparams, bodyparams, hastask) = commands[cmd]

        resource, resource_uri, tag1, tag2 = pathparams
        if resource_uri:
            path = resource_uri
            LOG.debug(_("[VRM-CINDER] [%s]"), path)
        else:
            path = self.site_uri + resource
            LOG.debug(_("[VRM-CINDER] [%s]"), path)
        if tag1:
            path += ('/' + str(tag1))
            LOG.debug(_("[VRM-CINDER] [%s]"), path)
        if tag2:
            path += ('/' + str(tag2))
            LOG.debug(_("[VRM-CINDER] [%s]"), path)

        if method == 'GET':
            query = self._joined_params(queryparams)
        elif method == 'DELETE':
            query = self._joined_params(queryparams)
        elif method == 'POST':
            query = self._joined_params(queryparams)
            LOG.info("[BRM-DRIVER] _generate_vrm_cmd bodyparams is [%s]", bodyparams)
            body = json.dumps(bodyparams)
            LOG.info("[BRM-DRIVER] _generate_vrm_cmd body is [%s]", body)
        else:
            raise cinder_exception.UnknownCmd(cmd=method)

        url = self._generate_url(path, query)
        LOG.info("[BRM-DRIVER] _generate_vrm_cmd url is [%s]", url)

        return (method, url, body, hastask)


