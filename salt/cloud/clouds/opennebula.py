# -*- coding: utf-8 -*-
'''
OpenNebula Cloud Module
=======================

The OpenNebula cloud module is used to control access to an OpenNebula cloud.

.. versionadded:: 2014.7.0

:depends: lxml

Use of this module requires the ``xml_rpc``, ``user``, and ``password``
parameters to be set.

Set up the cloud configuration at ``/etc/salt/cloud.providers`` or
``/etc/salt/cloud.providers.d/opennebula.conf``:

.. code-block:: yaml

    my-opennebula-config:
      xml_rpc: http://localhost:2633/RPC2
      user: oneadmin
      password: JHGhgsayu32jsa
      driver: opennebula

'''

# Import Python Libs
from __future__ import absolute_import
import logging
import os
import pprint
import time

# Import Salt Libs
import salt.config as config
from salt.exceptions import (
    SaltCloudConfigError,
    SaltCloudException,
    SaltCloudExecutionFailure,
    SaltCloudExecutionTimeout,
    SaltCloudNotFound,
    SaltCloudSystemExit
)
from salt.utils import is_true

# Import Salt Cloud Libs
import salt.utils.cloud

# Import Third Party Libs
try:
    import salt.ext.six.moves.xmlrpc_client  # pylint: disable=E0611
    from lxml import etree
    HAS_XML_LIBS = True
except ImportError:
    HAS_XML_LIBS = False

# Get Logging Started
log = logging.getLogger(__name__)

__virtualname__ = 'opennebula'


def __virtual__():
    '''
    Check for OpenNebula configs.
    '''
    if not HAS_XML_LIBS:
        return False

    if get_configured_provider() is False:
        return False

    return __virtualname__


def get_configured_provider():
    '''
    Return the first configured instance.
    '''
    return config.is_provider_configured(
        __opts__,
        __active_provider_name__ or 'opennebula',
        ('xml_rpc', 'user', 'password')
    )


def avail_images(call=None):
    '''
    Return available OpenNebula images.

    call
        Optional type of call to use with this function such as ``function``.

    CLI Example:

    .. code-block:: bash

        salt-cloud --list-images opennebula
        salt-cloud --function avail_images opennebula
        salt-cloud -f avail_images opennebula

    '''
    if call == 'action':
        raise SaltCloudSystemExit(
            'The avail_images function must be called with '
            '-f or --function, or with the --list-images option'
        )

    server, user, password = _get_xml_rpc()
    auth = ':'.join([user, password])
    image_pool = server.one.imagepool.info(auth, -1, -1, -1)[1]

    images = {}
    for image in etree.XML(image_pool):
        images[image.find('NAME').text] = _xml_to_dict(image)

    return images


def avail_locations(call=None):
    '''
    Return available OpenNebula locations.

    call
        Optional type of call to use with this function such as ``function``.

    CLI Example:

    .. code-block:: bash

        salt-cloud --list-locations opennebula
        salt-cloud --function avail_locations opennebula
        salt-cloud -f avail_locations opennebula

    '''
    if call == 'action':
        raise SaltCloudSystemExit(
            'The avail_locations function must be called with '
            '-f or --function, or with the --list-locations option'
        )

    server, user, password = _get_xml_rpc()
    auth = ':'.join([user, password])
    host_pool = server.one.hostpool.info(auth)[1]

    locations = {}
    for host in etree.XML(host_pool):
        locations[host.find('NAME').text] = _xml_to_dict(host)

    return locations


def avail_sizes():
    '''
    Because sizes are built into templates with OpenNebula, there will be no sizes to
    return here.
    '''
    log.info('Because sizes are built into templates with OpenNebula, '
             'there are no sizes to return.')
    return {}


def list_nodes(call=None):
    '''
    Return a list of VMs on OpenNebubla.

    call
        Optional type of call to use with this function such as ``function``.

    CLI Example:

    .. code-block:: bash

        salt-cloud -Q
        salt-cloud --query
        salt-cloud --fuction list_nodes opennebula
        salt-cloud -f list_nodes opennebula

    '''
    if call == 'action':
        raise SaltCloudException(
            'The list_nodes function must be called with -f or --function.'
        )

    return _list_nodes(full=False)


def list_nodes_full(call=None):
    '''
    Return a list of the VMs that are on the provider.

    call
        Optional type of call to use with this function such as ``function``.

    CLI Example:

    .. code-block:: bash

        salt-cloud -F
        salt-cloud --full-query
        salt-cloud --function list_nodes_full opennebula
        salt-cloud -f list_nodes_full opennebula

    '''
    if call == 'action':
        raise SaltCloudSystemExit(
            'The list_nodes_full function must be called with -f or --function.'
        )

    return _list_nodes(full=True)


def list_nodes_select(call=None):
    '''
    Return a list of the VMs that are on the provider, with select fields.

    call
        Optional type of call to use with this function such as ``function``.
    '''
    if call == 'action':
        raise SaltCloudSystemExit(
            'The list_nodes_full function must be called with -f or --function.'
        )

    return salt.utils.cloud.list_nodes_select(
        list_nodes_full('function'), __opts__['query.selection'], call,
    )


def get_image(vm_):
    '''
    Return the image object to use.

    vm_
        The VM for which to obtain an image.
    '''
    images = avail_images()
    vm_image = str(config.get_cloud_config_value(
        'image', vm_, __opts__, search_global=False
    ))
    for image in images:
        if vm_image in (images[image]['name'], images[image]['id']):
            return images[image]['id']
    raise SaltCloudNotFound(
        'The specified image, {0!r}, could not be found.'.format(vm_image)
    )


def get_image_id(kwargs=None, call=None):
    '''
    Returns an image's ID from the given image name.

    .. versionadded:: Boron

    CLI Example:

    .. code-block:: bash

        salt-cloud -f get_image_id opennebula name=my-image-name
    '''
    if call == 'action':
        raise SaltCloudSystemExit(
            'The get_image_id function must be called with -f or --function.'
        )

    if kwargs is None:
        kwargs = {}

    name = kwargs.get('name', None)
    if name is None:
        raise SaltCloudSystemExit(
            'The get_image_id function requires a name.'
        )

    return _list_images()[name]['id']


def get_location(vm_):
    '''
    Return the VM's location.

    vm_
        The VM for which to obtain a location.
    '''
    locations = avail_locations()
    vm_location = str(config.get_cloud_config_value(
        'location', vm_, __opts__, search_global=False
    ))

    if vm_location == 'None':
        return None

    for location in locations:
        if vm_location in (locations[location]['name'],
                           locations[location]['id']):
            return locations[location]['id']
    raise SaltCloudNotFound(
        'The specified location, {0!r}, could not be found.'.format(
            vm_location
        )
    )


def get_secgroup_id(kwargs=None, call=None):
    '''
    Returns a security group's ID from the given security group name.

    .. versionadded:: Boron

    CLI Example:

    .. code-block:: bash

        salt-cloud -f get_secgroup_id opennebula name=my-secgroup-name
    '''
    if call == 'action':
        raise SaltCloudSystemExit(
            'The get_secgroup_id function must be called with -f or --function.'
        )

    if kwargs is None:
        kwargs = {}

    name = kwargs.get('name', None)

    return _list_security_groups()[name]['id']


def get_template_id(kwargs=None, call=None):
    '''
    Returns a template's ID from the given template name.

    .. versionadded:: Boron

    CLI Example:

    .. code-block:: bash

        salt-cloud -f get_template_id opennebula name=my-template-name
    '''
    if call == 'action':
        raise SaltCloudSystemExit(
            'The list_nodes_full function must be called with -f or --function.'
        )

    if kwargs is None:
        kwargs = {}

    name = kwargs.get('name', None)

    if name is None:
        raise SaltCloudSystemExit(
            'The get_template_id function requires a name.'
        )

    return _get_template(name)['id']


def get_vm_id(kwargs=None, call=None):
    '''
    Returns a virtual machine's ID from the given virtual machine's name.

    .. versionadded:: Boron

    CLI Example:

    .. code-block:: bash

        salt-cloud -f get_vm_id opennebula name=my-vm
    '''
    if call == 'action':
        raise SaltCloudSystemExit(
            'The get_vm_id function must be called with -f or --function.'
        )

    if kwargs is None:
        kwargs = {}

    name = kwargs.get('name', None)
    if name is None:
        raise SaltCloudSystemExit(
            'The get_vm_id function requires a name.'
        )

    return _list_vms()[name]['id']


def get_vn_id(kwargs=None, call=None):
    '''
    Returns a virtual network's ID from the given virtual network's name.

    .. versionadded:: Boron

    CLI Example:

    .. code-block:: bash

        salt-cloud -f get_vn_id opennebula name=my-vn-name
    '''
    if call == 'action':
        raise SaltCloudSystemExit(
            'The get_vn_id function must be called with -f or --function.'
        )

    if kwargs is None:
        kwargs = {}

    name = kwargs.get('name', None)
    if name is None:
        raise SaltCloudSystemExit(
            'The get_vn_id function requires a name.'
        )

    return _list_vns()[name]['id']


def create(vm_):
    '''
    Create a single VM from a data dict.

    vm_
        The name of the VM to create.

    CLI Example:

    .. code-block:: bash

        salt-cloud -p my-opennebula-profile vm_name

    '''
    try:
        # Check for required profile parameters before sending any API calls.
        if config.is_profile_configured(__opts__,
                                        __active_provider_name__ or 'opennebula',
                                        vm_['profile']) is False:
            return False
    except AttributeError:
        pass

    # Since using "provider: <provider-engine>" is deprecated, alias provider
    # to use driver: "driver: <provider-engine>"
    if 'provider' in vm_:
        vm_['driver'] = vm_.pop('provider')

    salt.utils.cloud.fire_event(
        'event',
        'starting create',
        'salt/cloud/{0}/creating'.format(vm_['name']),
        {
            'name': vm_['name'],
            'profile': vm_['profile'],
            'provider': vm_['driver'],
        },
        transport=__opts__['transport']
    )

    log.info('Creating Cloud VM {0}'.format(vm_['name']))
    kwargs = {
        'name': vm_['name'],
        'image_id': get_image(vm_),
        'region_id': get_location(vm_),
    }

    private_networking = config.get_cloud_config_value(
        'private_networking', vm_, __opts__, search_global=False, default=None
    )
    kwargs['private_networking'] = 'true' if private_networking else 'false'

    salt.utils.cloud.fire_event(
        'event',
        'requesting instance',
        'salt/cloud/{0}/requesting'.format(vm_['name']),
        {'kwargs': kwargs},
    )

    region = ''
    if kwargs['region_id'] is not None:
        region = 'SCHED_REQUIREMENTS="ID={0}"'.format(kwargs['region_id'])
    try:
        server, user, password = _get_xml_rpc()
        auth = ':'.join([user, password])
        server.one.template.instantiate(auth,
                                        int(kwargs['image_id']),
                                        kwargs['name'],
                                        False,
                                        region)
    except Exception as exc:
        log.error(
            'Error creating {0} on OpenNebula\n\n'
            'The following exception was thrown when trying to '
            'run the initial deployment: {1}'.format(
                vm_['name'],
                str(exc)
            ),
            # Show the traceback if the debug logging level is enabled
            exc_info_on_loglevel=logging.DEBUG
        )
        return False

    def __query_node_data(vm_name):
        node_data = show_instance(vm_name, call='action')
        if not node_data:
            # Trigger an error in the wait_for_ip function
            return False
        if node_data['state'] == '7':
            return False
        if node_data['lcm_state'] == '3':
            return node_data

    try:
        data = salt.utils.cloud.wait_for_ip(
            __query_node_data,
            update_args=(vm_['name'],),
            timeout=config.get_cloud_config_value(
                'wait_for_ip_timeout', vm_, __opts__, default=10 * 60),
            interval=config.get_cloud_config_value(
                'wait_for_ip_interval', vm_, __opts__, default=2),
        )
    except (SaltCloudExecutionTimeout, SaltCloudExecutionFailure) as exc:
        try:
            # It might be already up, let's destroy it!
            destroy(vm_['name'])
        except SaltCloudSystemExit:
            pass
        finally:
            raise SaltCloudSystemExit(str(exc))

    key_filename = config.get_cloud_config_value(
        'private_key', vm_, __opts__, search_global=False, default=None
    )
    if key_filename is not None and not os.path.isfile(key_filename):
        raise SaltCloudConfigError(
            'The defined key_filename {0!r} does not exist'.format(
                key_filename
            )
        )

    try:
        private_ip = data['private_ips'][0]
    except KeyError:
        private_ip = data['template']['nic']['ip']

    ssh_username = config.get_cloud_config_value(
        'ssh_username', vm_, __opts__, default='root'
    )

    vm_['username'] = ssh_username
    vm_['key_filename'] = key_filename
    vm_['ssh_host'] = private_ip

    ret = salt.utils.cloud.bootstrap(vm_, __opts__)

    ret['id'] = data['id']
    ret['image'] = vm_['image']
    ret['name'] = vm_['name']
    ret['size'] = data['template']['memory']
    ret['state'] = data['state']
    ret['private_ips'] = private_ip
    ret['public_ips'] = []

    log.info('Created Cloud VM {0[name]!r}'.format(vm_))
    log.debug(
        '{0[name]!r} VM creation details:\n{1}'.format(
            vm_, pprint.pformat(data)
        )
    )

    salt.utils.cloud.fire_event(
        'event',
        'created instance',
        'salt/cloud/{0}/created'.format(vm_['name']),
        {
            'name': vm_['name'],
            'profile': vm_['profile'],
            'provider': vm_['driver'],
        },
    )

    return ret


def destroy(name, call=None):
    '''
    Destroy a node. Will check termination protection and warn if enabled.

    name
        The name of the vm to be destroyed.

    call
        Optional type of call to use with this function such as ``action``.

    CLI Example:

    .. code-block:: bash

        salt-cloud --destroy vm_name
        salt-cloud -d vm_name
        salt-cloud --action destroy vm_name
        salt-cloud -a destroy vm_name

    '''
    if call == 'function':
        raise SaltCloudSystemExit(
            'The destroy action must be called with -d, --destroy, '
            '-a or --action.'
        )

    salt.utils.cloud.fire_event(
        'event',
        'destroying instance',
        'salt/cloud/{0}/destroying'.format(name),
        {'name': name},
    )

    server, user, password = _get_xml_rpc()
    auth = ':'.join([user, password])

    data = show_instance(name, call='action')
    node = server.one.vm.action(auth, 'delete', int(data['id']))

    salt.utils.cloud.fire_event(
        'event',
        'destroyed instance',
        'salt/cloud/{0}/destroyed'.format(name),
        {'name': name},
    )

    if __opts__.get('update_cachedir', False) is True:
        salt.utils.cloud.delete_minion_cachedir(
            name,
            __active_provider_name__.split(':')[0],
            __opts__
        )

    data = {
        'action': 'vm.delete',
        'deleted': node[0],
        'node_id': node[1],
        'error_code': node[2]
    }

    return data


def image_allocate(call=None, kwargs=None):
    '''
    Allocates a new image in OpenNebula.

    .. versionadded:: Boron

    path
        The path to a file containing the template of the image to allocate.
        Syntax within the file can be the usual attribute=value or XML.

    datastore_id
        The ID of the data-store to be used for the new image.

    CLI Example:

    .. code-block:: bash

        salt-cloud -f image_allocate opennebula file=/path/to/image_file.txt datastore_id=1
    '''
    if call != 'function':
        raise SaltCloudSystemExit(
            'The image_allocate function must be called with -f or --function.'
        )

    if kwargs is None:
        kwargs = {}

    path = kwargs.get('path', None)
    datastore_id = kwargs.get('datastore_id', None)

    if not path or not datastore_id:
        raise SaltCloudSystemExit(
            'The image_allocate function requires a file \'path\' and a '
            '\'datastore_id\' to be provided.'
        )

    file_data = salt.utils.fopen(path, mode='r').read()
    server, user, password = _get_xml_rpc()
    auth = ':'.join([user, password])
    response = server.one.image.allocate(auth, file_data, int(datastore_id))

    data = {
        'action': 'image.allocate',
        'allocated': response[0],
        'image_id': response[1],
        'error_code': response[2],
    }

    return data


def image_clone(call=None, kwargs=None):
    '''
    Clones an existing image.

    .. versionadded:: Boron

    name
        The name of the new image.

    image_id
        The ID of the image to be cloned.

    CLI Example:

    .. code-block:: bash

        salt-cloud -f image_clone opennebula name=my-new-image image_id=10

    '''
    if call != 'function':
        raise SaltCloudSystemExit(
            'The image_clone function must be called with -f or --function.'
        )

    if kwargs is None:
        kwargs = {}

    name = kwargs.get('name', None)
    image_id = kwargs.get('image_id', None)

    if not name or not image_id:
        raise SaltCloudSystemExit(
            'The image_clone function requires a name and an image_id '
            'to be provided.'
        )

    server, user, password = _get_xml_rpc()
    auth = ':'.join([user, password])

    response = server.one.image.clone(auth, int(image_id), name)

    data = {
        'action': 'image.clone',
        'cloned': response[0],
        'cloned_image_id': response[1],
        'cloned_image_name': name,
        'error_code': response[2],
    }

    return data


def image_delete(call=None, kwargs=None):
    '''
    Deletes the given image from OpenNebula. Either a name or an image_id must
    be supplied.

    .. versionadded:: Boron

    name
        The name of the image to delete.

    image_id
        The ID of the image to delete.

    CLI Example:

    .. code-block:: bash

        salt-cloud -f image_delete opennebula name=my-image
        salt-cloud --function image_delete opennebula image_id=100
    '''
    if call != 'function':
        raise SaltCloudSystemExit(
            'The image_delete function must be called with -f or --function.'
        )

    if kwargs is None:
        kwargs = {}

    name = kwargs.get('name', None)
    image_id = kwargs.get('image_id', None)

    if not name and not image_id:
        raise SaltCloudSystemExit(
            'The image_delete function requires a name or an image_id '
            'to be provided.'
        )

    server, user, password = _get_xml_rpc()
    auth = ':'.join([user, password])

    if name and not image_id:
        image_id = get_image_id(kwargs={'name': name})

    response = server.one.image.delete(auth, int(image_id))

    data = {
        'action': 'image.delete',
        'deleted': response[0],
        'image_id': response[1],
        'error_code': response[2],
    }

    return data


def image_info(call=None, kwargs=None):
    '''
    Retrieves information for a given image. Either a name or an image_id must be
    supplied.

    .. versionadded:: Boron

    name
        The name of the image for which to gather information.

    template_id
        The ID of the image for which to gather information.

    CLI Example:

    .. code-block:: bash

        salt-cloud -f image_info opennebula name=my-image
        salt-cloud --function image_info opennebula image_id=5
    '''
    if call != 'function':
        raise SaltCloudSystemExit(
            'The image_info function must be called with -f or --function.'
        )

    if kwargs is None:
        kwargs = {}

    name = kwargs.get('name', None)
    image_id = kwargs.get('image_id', None)

    if not name and not image_id:
        raise SaltCloudSystemExit(
            'The image_info function requires either a name or an image_id '
            'to be provided.'
        )

    server, user, password = _get_xml_rpc()
    auth = ':'.join([user, password])

    if name and not image_id:
        image_id = get_image_id(kwargs={'name': name})

    info = {}
    response = server.one.image.info(auth, int(image_id))[1]
    tree = etree.XML(response)
    info[tree.find('NAME').text] = _xml_to_dict(tree)

    return info


def image_persistent(call=None, kwargs=None):
    '''
    Sets the Image as persistent or not persistent.

    .. versionadded:: Boron

    name
        The name of the image to set.

    persist
        A boolean value to set the image as persistent or not. Set to true
        for persistent, false for non-persisent.

    template_id
        The ID of the image to set.

    CLI Example:

    .. code-block:: bash

        salt-cloud -f image_persistent opennebula name=my-image
        salt-cloud --function image_persistent opennebula image_id=5
    '''
    if call != 'function':
        raise SaltCloudSystemExit(
            'The image_persistent function must be called with -f or --function.'
        )

    if kwargs is None:
        kwargs = {}

    name = kwargs.get('name', None)
    persist = kwargs.get('persist', None)
    image_id = kwargs.get('image_id', None)

    if not name and not image_id:
        raise SaltCloudSystemExit(
            'The image_persistent function requires either a name or an image_id '
            'to be provided.'
        )

    if not persist:
        raise SaltCloudSystemExit(
            'The image_persistent function requires \'persist\' to be set to \'True\' '
            'or \'False\'.'
        )

    server, user, password = _get_xml_rpc()
    auth = ':'.join([user, password])

    if name and not image_id:
        image_id = get_image_id(kwargs={'name': name})

    response = server.one.image.persistent(auth, int(image_id), is_true(persist))

    data = {
        'action': 'image.persistent',
        'response': response[0],
        'image_id': response[1],
        'error_code': response[2],
    }

    return data


def image_update(call=None, kwargs=None):
    '''
    Replaces the image template contents.

    .. versionadded:: Boron

    image_id
        The ID of the image to update.

    path
        The path to a file containing the template of the image. Syntax within the
        file can be the usual attribute=value or XML.

    update_type
        There are two ways to update an image: ``replace`` the whole template
        or ``merge`` the new template with the existing one.

    CLI Example:

    .. code-block:: bash

        salt-cloud -f image_update opennebula image_id=0 file=/path/to/image_update_file.txt update_type=replace
    '''
    if call != 'function':
        raise SaltCloudSystemExit(
            'The image_allocate function must be called with -f or --function.'
        )

    if kwargs is None:
        kwargs = {}

    image_id = kwargs.get('image_id', None)
    path = kwargs.get('path', None)
    update_type = kwargs.get('update_type', None)
    update_args = ['replace', 'merge']

    if not image_id or not path or not update_type:
        raise SaltCloudSystemExit(
            'The image_update function requires an \'image_id\', a file \'path\', '
            'and an \'update_type\' to be provided.'
        )

    if update_type == update_args[0]:
        update_number = 0
    elif update_type == update_args[1]:
        update_number = 1
    else:
        raise SaltCloudSystemExit(
            'The update_type argument must be either {0} or {1}.'.format(
                update_args[0],
                update_args[1]
            )
        )

    server, user, password = _get_xml_rpc()
    auth = ':'.join([user, password])
    file_data = salt.utils.fopen(path, mode='r').read()
    response = server.one.image.update(auth, int(image_id), file_data, int(update_number))

    data = {
        'action': 'image.update',
        'updated': response[0],
        'image_id': response[1],
        'error_code': response[2],
    }

    return data


def script(vm_):
    '''
    Return the script deployment object.

    vm_
        The VM for which to deploy a script.
    '''
    deploy_script = salt.utils.cloud.os_script(
        config.get_cloud_config_value('script', vm_, __opts__),
        vm_,
        __opts__,
        salt.utils.cloud.salt_config_to_yaml(
            salt.utils.cloud.minion_config(__opts__, vm_)
        )
    )
    return deploy_script


def show_instance(name, call=None):
    '''
    Show the details from OpenNebula concerning a named VM.

    name
        The name of the VM for which to display details.

    call
        Type of call to use with this function such as ``function``.

    CLI Example:

    .. code-block:: bash

        salt-cloud --action show_instance vm_name
        salt-cloud -a show_instance vm_name

    '''
    if call != 'action':
        raise SaltCloudSystemExit(
            'The show_instance action must be called with -a or --action.'
        )

    node = _get_node(name)
    salt.utils.cloud.cache_node(node, __active_provider_name__, __opts__)

    return node


def secgroup_allocate(call=None, kwargs=None):
    '''
    Allocates a new security group in OpenNebula.

    .. versionadded:: Boron

    path
        The path to a file containing the template of the security group. Syntax
        within the file can be the usual attribute=value or XML.

    CLI Example:

    .. code-block:: bash

        salt-cloud -f secgroup_allocate opennebula file=/path/to/secgroup_file.txt
    '''
    if call != 'function':
        raise SaltCloudSystemExit(
            'The secgroup_allocate function must be called with -f or --function.'
        )

    if kwargs is None:
        kwargs = {}

    path = kwargs.get('path', None)
    if not path:
        raise SaltCloudSystemExit(
            'The secgroup_allocate function requires a file path to be provided.'
        )

    data = salt.utils.fopen(path, mode='r').read()

    server, user, password = _get_xml_rpc()
    auth = ':'.join([user, password])

    response = server.one.secgroup.allocate(auth, data)

    data = {
        'action': 'secgroup.allocate',
        'allocated': response[0],
        'secgroup_id': response[1],
        'error_code': response[2],
    }

    return data


def secgroup_clone(call=None, kwargs=None):
    '''
    Clones an existing security group.

    .. versionadded:: Boron

    name
        The name of the new template.

    secgroup_id
        The ID of the template to be cloned.

    CLI Example:

    .. code-block:: bash

        salt-cloud -f secgroup_clone opennebula name=my-cloned-secgroup secgroup_id=0

    '''
    if call == 'action':
        raise SaltCloudSystemExit(
            'The secgroup_clone function must be called with -f or --function.'
        )

    if kwargs is None:
        kwargs = {}

    name = kwargs.get('name', None)
    secgroup_id = kwargs.get('secgroup_id', None)

    if not name or not secgroup_id:
        raise SaltCloudSystemExit(
            'The secgroup_clone function requires a name and a secgroup_id '
            'to be provided.'
        )

    server, user, password = _get_xml_rpc()
    auth = ':'.join([user, password])

    response = server.one.secgroup.clone(auth, int(secgroup_id), name)

    data = {
        'action': 'secgroup.clone',
        'cloned': response[0],
        'cloned_secgroup_id': response[1],
        'cloned_secgroup_name': name,
        'error_code': response[2],
    }

    return data


def secgroup_delete(call=None, kwargs=None):
    '''
    Deletes the given security group from OpenNebula. Either a name or a secgroup_id
    must be supplied.

    .. versionadded:: Boron

    name
        The name of the security group to delete.

    secgroup_id
        The ID of the security group to delete.

    CLI Example:

    .. code-block:: bash

        salt-cloud -f secgroup_delete opennebula name=my-secgroup
        salt-cloud --function secgroup_delete opennebula secgroup_id=100
    '''
    if call == 'action':
        raise SaltCloudSystemExit(
            'The secgroup_delete function must be called with -f or --function.'
        )

    if kwargs is None:
        kwargs = {}

    name = kwargs.get('name', None)
    secgroup_id = kwargs.get('secgroup_id', None)

    if not name and not secgroup_id:
        raise SaltCloudSystemExit(
            'The secgroup_delete function requires either a name or a secgroup_id '
            'to be provided.'
        )

    server, user, password = _get_xml_rpc()
    auth = ':'.join([user, password])

    if name and not secgroup_id:
        secgroup_id = get_secgroup_id(kwargs={'name': name})

    response = server.one.secgroup.delete(auth, int(secgroup_id))

    data = {
        'action': 'secgroup.delete',
        'deleted': response[0],
        'secgroup_id': response[1],
        'error_code': response[2],
    }

    return data


def secgroup_info(call=None, kwargs=None):
    '''
    Retrieves information for the given security group. Either a name or a
    secgroup_id must be supplied.

    name
        The name of the security group for which to gather information.

    template_id
        The ID of the security group for which to gather information.

    CLI Example:

    .. code-block:: bash

        salt-cloud -f secgroup_info opennebula name=my-secgroup
        salt-cloud --function secgroup_info opennebula secgroup_id=5
    '''
    if call == 'action':
        raise SaltCloudSystemExit(
            'The secgroup_info function must be called with -f or --function.'
        )

    if kwargs is None:
        kwargs = {}

    name = kwargs.get('name', None)
    secgroup_id = kwargs.get('secgroup_id', None)

    if not name and not secgroup_id:
        raise SaltCloudSystemExit(
            'The secgroup_info function requires either a name or a secgroup_id '
            'to be provided.'
        )

    server, user, password = _get_xml_rpc()
    auth = ':'.join([user, password])

    if name and not secgroup_id:
        secgroup_id = get_secgroup_id(kwargs={'name': name})

    info = {}
    response = server.one.secgroup.info(auth, int(secgroup_id))[1]
    tree = etree.XML(response)
    info[tree.find('NAME').text] = _xml_to_dict(tree)

    return info


def secgroup_update(call=None, kwargs=None):
    '''
    Replaces the security group template contents.

    .. versionadded:: Boron

    secgroup_id
        The ID of the security group to update.

    path
        The path to a file containing the template of the security group. Syntax
        within the file can be the usual attribute=value or XML.

    update_type
        There are two ways to update a security group: ``replace`` the whole template
        or ``merge`` the new template with the existing one.

    CLI Example:

    .. code-block:: bash

        salt-cloud --function secgroup_update opennebula secgroup_id=100 \
            file=/path/to/secgroup_update_file.txt \
            update_type=replace
    '''
    if call != 'function':
        raise SaltCloudSystemExit(
            'The secgroup_allocate function must be called with -f or --function.'
        )

    if kwargs is None:
        kwargs = {}

    secgroup_id = kwargs.get('secgroup_id', None)
    path = kwargs.get('path', None)
    update_type = kwargs.get('update_type', None)
    update_args = ['replace', 'merge']

    if not secgroup_id or not path or not update_type:
        raise SaltCloudSystemExit(
            'The secgroup_update function requires a \'secgroup_id\', a file \'path\', '
            'and an \'update_type\' to be provided.'
        )

    if update_type == update_args[0]:
        update_number = 0
    elif update_type == update_args[1]:
        update_number = 1
    else:
        raise SaltCloudSystemExit(
            'The update_type argument must be either {0} or {1}.'.format(
                update_args[0],
                update_args[1]
            )
        )

    server, user, password = _get_xml_rpc()
    auth = ':'.join([user, password])
    file_data = salt.utils.fopen(path, mode='r').read()
    response = server.one.secgroup.update(auth, int(secgroup_id), file_data, int(update_number))

    data = {
        'action': 'secgroup.update',
        'updated': response[0],
        'secgroup_id': response[1],
        'error_code': response[2],
    }

    return data


def template_allocate(call=None, kwargs=None):
    '''
    Allocates a new template in OpenNebula.

    .. versionadded:: Boron

    path
        The path to a file containing the elements of the template to be allocated.
        Syntax within the file can be the usual attribute=value or XML.

    CLI Example:

    .. code-block:: bash

        salt-cloud -f template_allocate opennebula path=/path/to/template_file.txt
    '''
    if call != 'function':
        raise SaltCloudSystemExit(
            'The template_allocate function must be called with -f or --function.'
        )

    if kwargs is None:
        kwargs = {}

    path = kwargs.get('path', None)
    if not path:
        raise SaltCloudSystemExit(
            'The template_allocate function requires a file path to be provided.'
        )

    path_data = salt.utils.fopen(path, mode='r').read()
    server, user, password = _get_xml_rpc()
    auth = ':'.join([user, password])
    response = server.one.template.allocate(auth, path_data)

    data = {
        'action': 'template.allocate',
        'allocated': response[0],
        'template_id': response[1],
        'error_code': response[2],
    }

    return data


def template_clone(call=None, kwargs=None):
    '''
    Clones an existing virtual machine template.

    .. versionadded:: Boron

    name
        The name of the new template.

    template_id
        The ID of the template to be cloned.

    CLI Example:

    .. code-block:: bash

        salt-cloud -f template_clone opennebula name=my-cloned-template template_id=0

    '''
    if call == 'action':
        raise SaltCloudSystemExit(
            'The template_clone function must be called with -f or --function.'
        )

    if kwargs is None:
        kwargs = {}

    name = kwargs.get('name', None)
    template_id = kwargs.get('template_id', None)

    if not name or not template_id:
        raise SaltCloudSystemExit(
            'The template_clone function requires a name and a template_id '
            'to be provided.'
        )

    server, user, password = _get_xml_rpc()
    auth = ':'.join([user, password])

    response = server.one.template.clone(auth, int(template_id), name)

    data = {
        'action': 'template.clone',
        'cloned': response[0],
        'cloned_template_id': response[1],
        'cloned_template_name': name,
        'error_code': response[2],
    }

    return data


def template_delete(call=None, kwargs=None):
    '''
    Deletes the given template from OpenNebula. Either a name or a template_id must
    be supplied.

    .. versionadded:: Boron

    name
        The name of the template to delete.

    template_id
        The ID of the template to delete.

    CLI Example:

    .. code-block:: bash

        salt-cloud -f template_delete opennebula name=my-template
        salt-cloud --function template_delete opennebula template_id=5
    '''
    if call == 'action':
        raise SaltCloudSystemExit(
            'The template_delete function must be called with -f or --function.'
        )

    if kwargs is None:
        kwargs = {}

    name = kwargs.get('name', None)
    template_id = kwargs.get('template_id', None)

    if not name and not template_id:
        raise SaltCloudSystemExit(
            'The template_delete function requires either a name or a template_id '
            'to be provided.'
        )

    # Make the API call to O.N. once and pass them to other functions that need them.
    server, user, password = _get_xml_rpc()
    auth = ':'.join([user, password])

    if template_id and name:
        _check_name_id_collisions(name,
                                  template_id,
                                  server=server,
                                  user=user,
                                  password=password)

    if name and not template_id:
        template_id = get_template_id(kwargs={'name': name})

    response = server.one.template.delete(auth, int(template_id))

    data = {
        'action': 'template.delete',
        'deleted': response[0],
        'template_id': response[1],
        'error_code': response[2],
    }

    return data


def template_instantiate(call=None, kwargs=None):
    '''
    Instantiates a new virtual machine from a template.

    .. versionadded:: Boron

    .. note::
        ``template_instantiate`` creates a VM on OpenNebula from a template, but it
        does not install Salt on the new VM. Use the ``create`` function for that
        functionality: ``salt-cloud -p opennebula-profile vm-name``.

    vm_name
        Name for the new VM instance.

    template_id
        The ID of the template from which the VM will be created.

    CLI Example:

    .. code-block:: bash

        salt-cloud -f template_instantiate opennebula vm_name=my-new-vm template_id=0

    '''
    if call == 'action':
        raise SaltCloudSystemExit(
            'The template_instantiate function must be called with -f or --function.'
        )

    if kwargs is None:
        kwargs = {}

    vm_name = kwargs.get('vm_name', None)
    template_id = kwargs.get('template_id', None)

    if not vm_name or not template_id:
        raise SaltCloudSystemExit(
            'The template_instantiate function requires a vm_name and a template_id '
            'to be provided.'
        )

    server, user, password = _get_xml_rpc()
    auth = ':'.join([user, password])

    response = server.one.template.instantiate(auth, int(template_id), vm_name)

    data = {
        'action': 'template.instantiate',
        'instantiated': response[0],
        'instantiated_vm_id': response[1],
        'vm_name': vm_name,
        'error_code': response[2],
    }

    return data


def vm_action(name=None, action=None, call=None):
    '''
    Submits an action to be performed on a given virtual machine.

    .. versionadded:: Boron

    name
        The name of the VM to action.
        
    action
        The action to be performed on the VM. Available options include:
          - boot
          - delete
          - delete-recreate
          - hold
          - poweroff
          - poweroff-hard
          - shutdown
          - shutdown-hard
          - stop
          - suspend
          - reboot
          - reboot-hard
          - release
          - resched
          - resume
          - undeploy
          - undeploy-hard
          - unresched

    CLI Example:

    .. code-block:: bash

        salt-cloud -a vm_action my-vm
    '''
    if call != 'action':
        raise SaltCloudSystemExit(
            'The vm_info action must be called with -a or --action.'
        )

    server, user, password = _get_xml_rpc()
    auth = ':'.join([user, password])
    vm_id = int(get_vm_id(kwargs={'name': name}))
    response = server.one.vm.action(auth, action, vm_id)

    data = {
        'action': 'vm.action.' + action,
        'actioned': response[0],
        'vm_id': response[1],
        'error_code': response[2],
    }

    return data


def vm_allocate(call=None, kwargs=None):
    '''
    Allocates a new virtual machine in OpenNebula.

    .. versionadded:: Boron

    path
        The path to a file defining the template of the VM to allocate.
        Syntax within the file can be the usual attribute=value or XML.

    hold
        If this parameter is set to ``True``, the VM will be created in
        the ``HOLD`` state. If not set, the VM is created in the ``PENDING``
        state. Default is ``False``.

    CLI Example:

    .. code-block:: bash

        salt-cloud -f vm_allocate path=/path/to/vm_template.txt
        salt-cloud --function vm_allocate path=/path/to/vm_template.txt hold=True
    '''
    if call != 'function':
        raise SaltCloudSystemExit(
            'The vm_allocate function must be called with -f or --function.'
        )

    if kwargs is None:
        kwargs = {}

    path = kwargs.get('path', None)
    hold = kwargs.get('hold', None)

    if not path:
        raise SaltCloudSystemExit(
            'The vm_allocate function requires a file \'path\' to be provided.'
        )

    file_data = salt.utils.fopen(path, mode='r').read()
    server, user, password = _get_xml_rpc()
    auth = ':'.join([user, password])
    response = server.one.vm.allocate(auth, file_data, is_true(hold))

    data = {
        'action': 'vm.allocate',
        'allocated': response[0],
        'vm_id': response[1],
        'error_code': response[2],
    }

    return data


def vm_info(name=None, call=None):
    '''
    Retrieves information for a given virtual machine. A VM name must be supplied.

    .. versionadded:: Boron

    name
        The name of the VM for which to gather information.

    CLI Example:

    .. code-block:: bash

        salt-cloud -a vm_info my-vm
    '''
    if call != 'action':
        raise SaltCloudSystemExit(
            'The vm_info action must be called with -a or --action.'
        )

    server, user, password = _get_xml_rpc()
    auth = ':'.join([user, password])
    vm_id = int(get_vm_id(kwargs={'name': name}))
    response = server.one.vm.info(auth, vm_id)

    if response[0] is False:
        return response[1]
    else:
        info = {}
        tree = etree.XML(response[1])
        info[tree.find('NAME').text] = _xml_to_dict(tree)
        return info


def vm_monitoring(name=None, call=None):
    '''
    Returns the monitoring records for a given virtual machine. A VM name must be
    supplied.

    The monitoring information returned is a list of VM elements. Each VM element
    contains the complete dictionary of the VM with the updated information returned
    by the poll action.

    .. versionadded:: Boron

    name
        The name of the VM of which to gather monitoring records.

    CLI Example:

    .. code-block:: bash

        salt-cloud -a vm_monitoring my-vm
    '''
    if call != 'action':
        raise SaltCloudSystemExit(
            'The vm_monitoring action must be called with -a or --action.'
        )

    server, user, password = _get_xml_rpc()
    auth = ':'.join([user, password])
    vm_id = int(get_vm_id(kwargs={'name': name}))
    response = server.one.vm.monitoring(auth, vm_id)

    if response[0] is False:
        log.error(
            'There was an error retrieving the specified VM\'s monitoring information.'
        )
        return {}
    else:
        info = {}
        for vm_ in etree.XML(response[1]):
            info[vm_.find('ID').text] = _xml_to_dict(vm_)
        return info


def vn_add_ar(call=None, kwargs=None):
    '''
    Adds address ranges to a given virtual network.

    .. versionadded:: Boron

    vn_id
        The ID of the virtual network to add the address range.

    path
        The path to a file containing the template of the address range to add.
        Syntax within the file can be the usual attribute=value or XML.

    CLI Example:

    .. code-block:: bash

        salt-cloud -f vn_add_ar opennbula vn_id=3 path=/path/to/address_range.txt
    '''
    if call != 'function':
        raise SaltCloudSystemExit(
            'The vn_add_ar function must be called with -f or --function.'
        )

    if kwargs is None:
        kwargs = {}

    vn_id = kwargs.get('vn_id', None)
    path = kwargs.get('path', None)

    if not vn_id and not path:
        raise SaltCloudSystemExit(
            'The vn_add_ar function requires a \'vn_id\' and a file \'path\' to '
            'be provided.'
        )

    file_data = salt.utils.fopen(path, mode='r').read()
    server, user, password = _get_xml_rpc()
    auth = ':'.join([user, password])
    response = server.one.vn.add_ar(auth, int(vn_id), file_data)

    data = {
        'action': 'vn.add_ar',
        'address_range_added': response[0],
        'resource_id': response[1],
        'error_code': response[2],
    }

    return data


def vn_allocate(call=None, kwargs=None):
    '''
    Allocates a new virtual network in OpenNebula.

    .. versionadded:: Boron

    path
        The path to a file containing the template of the virtual network to allocate.
        Syntax within the file can be the usual attribute=value or XML.

    cluster_id
        The ID of the cluster for which to add the new virtual network. If not provided,
        the virtual network won’t be added to any cluster.

    CLI Example:

    .. code-block:: bash

        salt-cloud -f vn_allocate opennebula path=/path/to/vn_file.txt
    '''
    if call != 'function':
        raise SaltCloudSystemExit(
            'The secgroup_allocate function must be called with -f or --function.'
        )

    if kwargs is None:
        kwargs = {}

    cluster_id = kwargs.get('cluster_id', '-1')
    path = kwargs.get('path', None)
    if not path:
        raise SaltCloudSystemExit(
            'The vn_allocate function requires a file \'path\' to be provided.'
        )

    file_data = salt.utils.fopen(path, mode='r').read()
    server, user, password = _get_xml_rpc()
    auth = ':'.join([user, password])
    response = server.one.vn.allocate(auth, file_data, int(cluster_id))

    data = {
        'action': 'vn.allocate',
        'allocated': response[0],
        'vn_id': response[1],
        'error_code': response[2],
    }

    return data


def vn_delete(call=None, kwargs=None):
    '''
    Deletes the given virtual network from OpenNebula. Either a name or a vn_id must
    be supplied.

    .. versionadded:: Boron

    name
        The name of the virtual network to delete.

    vn_id
        The ID of the virtual network to delete.

    CLI Example:

    .. code-block:: bash

        salt-cloud -f vn_delete opennebula name=my-virtual-network
        salt-cloud --function vn_delete opennebula vn_id=3
    '''
    if call != 'function':
        raise SaltCloudSystemExit(
            'The vn_delete function must be called with -f or --function.'
        )

    if kwargs is None:
        kwargs = {}

    name = kwargs.get('name', None)
    vn_id = kwargs.get('vn_id', None)

    if not name and not vn_id:
        raise SaltCloudSystemExit(
            'The vn_delete function requires a name or a vn_id '
            'to be provided.'
        )

    server, user, password = _get_xml_rpc()
    auth = ':'.join([user, password])

    if name and not vn_id:
        vn_id = get_image_id(kwargs={'name': name})

    response = server.one.image.delete(auth, int(vn_id))

    data = {
        'action': 'vn.delete',
        'deleted': response[0],
        'vn_id': response[1],
        'error_code': response[2],
    }

    return data


def vn_free_ar(call=None, kwargs=None):
    '''
    Frees a reserved address range from a virtual network.

    .. versionadded:: Boron

    vn_id
        The ID of the virtual network from which to free an address range.

    ar_id
        The ID of the address range to free.

    CLI Example:

    .. code-block:: bash

        salt-cloud -f vn_free_ar opennebula vn_id=3 ar_id=1
    '''
    if call != 'function':
        raise SaltCloudSystemExit(
            'The vn_free_ar function must be called with -f or --function.'
        )

    if kwargs is None:
        kwargs = {}

    vn_id = kwargs.get('vn_id', None)
    ar_id = kwargs.get('ar_id', None)

    if not vn_id or not ar_id:
        raise SaltCloudSystemExit(
            'The vn_free_ar function requires a vn_id and an rn_id '
            'to be provided.'
        )

    server, user, password = _get_xml_rpc()
    auth = ':'.join([user, password])
    response = server.one.vn.free_ar(auth, int(vn_id), int(ar_id))

    data = {
        'action': 'vn.free_ar',
        'ar_freed': response[0],
        'resource_id': response[1],
        'error_code': response[2],
    }

    return data


def vn_hold(call=None, kwargs=None):
    '''
    Holds a virtual network lease as used.

    .. versionadded:: Boron

    vn_id
        The ID of the virtual network from which to hold the lease.

    path
        The path to a file defining the template of the lease to hold.
        Syntax within the file can be the usual attribute=value or XML.

    CLI Example:

    .. code-block:: bash

        salt-cloud -f vn_hold opennebula vn_id=3 path=/path/to/vn_hold_file.txt
    '''
    if call != 'function':
        raise SaltCloudSystemExit(
            'The vn_hold function must be called with -f or --function.'
        )

    if kwargs is None:
        kwargs = {}

    vn_id = kwargs.get('vn_id', None)
    path = kwargs.get('path', None)

    if not vn_id or not path:
        raise SaltCloudSystemExit(
            'The vn_hold function requires a \'vn_id\' and a \'path\' '
            'to be provided.'
        )

    file_data = salt.utils.fopen(path, mode='r').read()
    server, user, password = _get_xml_rpc()
    auth = ':'.join([user, password])
    response = server.one.vn.hold(auth, int(vn_id), file_data)

    data = {
        'action': 'vn.hold',
        'held': response[0],
        'resource_id': response[1],
        'error_code': response[2],
    }

    return data


def vn_info(call=None, kwargs=None):
    '''
    Retrieves information for the virtual network.

    .. versionadded:: Boron

    name
        The name of the virtual network for which to gather information.

    vn_id
        The ID of the virtual network for which to gather information.

    CLI Example:

    .. code-block:: bash

        salt-cloud -f vn_info opennebula vn_id=3
        salt-cloud --function vn_info opennebula name=public
    '''
    if call != 'function':
        raise SaltCloudSystemExit(
            'The vn_info function must be called with -f or --function.'
        )

    if kwargs is None:
        kwargs = {}

    name = kwargs.get('name', None)
    vn_id = kwargs.get('vn_id', None)

    if not name and not vn_id:
        raise SaltCloudSystemExit(
            'The vn_info function requires either a name or a vn_id '
            'to be provided.'
        )

    server, user, password = _get_xml_rpc()
    auth = ':'.join([user, password])

    if name and not vn_id:
        vn_id = get_vn_id(kwargs={'name': name})

    response = server.one.vn.info(auth, int(vn_id))

    if response[0] is False:
        return response[1]
    else:
        info = {}
        tree = etree.XML(response[1])
        info[tree.find('NAME').text] = _xml_to_dict(tree)
        return info


def vn_release(call=None, kwargs=None):
    '''
    Releases a virtual network lease that was previously on hold.

    .. versionadded:: Boron

    vn_id
        The ID of the virtual network from which to release the lease.

    path
        The path to a file defining the template of the lease to release.
        Syntax within the file can be the usual attribute=value or XML.

    CLI Example:

    .. code-block:: bash

        salt-cloud -f vn_release opennebula vn_id=3 path=/path/to/vn_release_file.txt
    '''
    if call != 'function':
        raise SaltCloudSystemExit(
            'The vn_reserve function must be called with -f or --function.'
        )

    if kwargs is None:
        kwargs = {}

    vn_id = kwargs.get('vn_id', None)
    path = kwargs.get('path', None)

    if not vn_id or not path:
        raise SaltCloudSystemExit(
            'The vn_release function requires a \'vn_id\' and a \'path\' '
            'to be provided.'
        )

    file_data = salt.utils.fopen(path, mode='r').read()
    server, user, password = _get_xml_rpc()
    auth = ':'.join([user, password])
    response = server.one.vn.release(auth, int(vn_id), file_data)

    data = {
        'action': 'vn.release',
        'released': response[0],
        'resource_id': response[1],
        'error_code': response[2],
    }

    return data


def vn_reserve(call=None, kwargs=None):
    '''
    Reserve network addresses.

    .. versionadded:: Boron

    vn_id
        The ID of the virtual network from which to reserve addresses.

    path
        The path to a file defining the template of the address reservation.
        Syntax within the file can be the usual attribute=value or XML.

    CLI Example:

    .. code-block:: bash

        salt-cloud -f vn_reserve opennebula vn_id=3 path=/path/to/vn_reserve_file.txt
    '''
    if call != 'function':
        raise SaltCloudSystemExit(
            'The vn_reserve function must be called with -f or --function.'
        )

    if kwargs is None:
        kwargs = {}

    vn_id = kwargs.get('vn_id', None)
    path = kwargs.get('path', None)

    if not vn_id or not path:
        raise SaltCloudSystemExit(
            'The vn_reserve function requires a \'vn_id\' and a \'path\' '
            'to be provided.'
        )

    file_data = salt.utils.fopen(path, mode='r').read()
    server, user, password = _get_xml_rpc()
    auth = ':'.join([user, password])
    response = server.one.vn.reserve(auth, int(vn_id), file_data)

    data = {
        'action': 'vn.reserve',
        'reserved': response[0],
        'resource_id': response[1],
        'error_code': response[2],
    }

    return data


def template_update(call=None, kwargs=None):
    '''
    Replaces the template contents.

    .. versionadded:: Boron

    template_id
        The ID of the template to update.

    path
        The path to a file containing the elements of the template to be updated.
        Syntax within the file can be the usual attribute=value or XML.

    update_type
        There are two ways to update a template: ``replace`` the whole template
        or ``merge`` the new template with the existing one.

    CLI Example:

    .. code-block:: bash

        salt-cloud --function template_update opennebula template_id=1 \
            path=/path/to/template_update_file.txt \
            update_type=replace
    '''
    if call != 'function':
        raise SaltCloudSystemExit(
            'The template_update function must be called with -f or --function.'
        )

    if kwargs is None:
        kwargs = {}

    template_id = kwargs.get('template_id', None)
    path = kwargs.get('path', None)
    update_type = kwargs.get('update_type', None)
    update_args = ['replace', 'merge']

    if not template_id or not path or not update_type:
        raise SaltCloudSystemExit(
            'The template_update function requires a \'template_id\', a file \'path\', '
            'and an \'update_type\' to be provided.'
        )

    if update_type == update_args[0]:
        update_number = 0
    elif update_type == update_args[1]:
        update_number = 1
    else:
        raise SaltCloudSystemExit(
            'The update_type argument must be either {0} or {1}.'.format(
                update_args[0],
                update_args[1]
            )
        )

    path_data = salt.utils.fopen(path, mode='r').read()
    server, user, password = _get_xml_rpc()
    auth = ':'.join([user, password])
    response = server.one.template.update(auth, int(template_id), path_data, int(update_number))

    data = {
        'action': 'template.update',
        'updated': response[0],
        'template_id': response[1],
        'error_code': response[2],
    }

    return data


# Helper Functions

def _check_name_id_collisions(name, id_, server=None, user=None, password=None):
    '''
    Helper function that ensures that a provided name and provided id match.
    '''
    name_id = _get_template(name,
                            server=server,
                            user=user,
                            password=password)['id']
    if name_id != id_:
        raise SaltCloudException(
            'A name and an ID were provided, but the provided id, \'{0}\', does '
            'not match the ID found for the provided name: \'{1}\': \'{2}\'. '
            'Nothing was done.'.format(
                id_,
                name,
                name_id
            )
        )


def _get_node(name):
    '''
    Helper function that returns all information about a named node.

    name
        The name of the node for which to get information.
    '''
    attempts = 10

    while attempts >= 0:
        try:
            return list_nodes_full()[name]
        except KeyError:
            attempts -= 1
            log.debug(
                'Failed to get the data for the node {0!r}. Remaining '
                'attempts {1}'.format(
                    name, attempts
                )
            )

            # Just a little delay between attempts...
            time.sleep(0.5)

    return {}


def _get_template(name, server=None, user=None, password=None):
    '''
    Helper function returning all information about a named template.

    name
        The name of the template for which to obtain information.
    '''
    attempts = 10

    while attempts >= 0:
        try:
            return _list_templates(
                server=server,
                user=user,
                password=password)[name]
        except KeyError:
            attempts -= 1
            log.debug(
                'Failed to get the data for the template {0!r}. Remaining '
                'attempts {1}'.format(
                    name, attempts
                )
            )
            # Just a little delay between attempts...
            time.sleep(0.5)

    return {}


def _get_xml_rpc():
    '''
    Uses the OpenNebula cloud provider configurations to connect to the
    OpenNebula API.

    Returns the server connection created as well as the user and password
    values from the cloud provider config file used to make the connection.
    '''
    vm_ = get_configured_provider()

    xml_rpc = config.get_cloud_config_value(
        'xml_rpc', vm_, __opts__, search_global=False
    )

    user = config.get_cloud_config_value(
        'user', vm_, __opts__, search_global=False
    )

    password = config.get_cloud_config_value(
        'password', vm_, __opts__, search_global=False
    )

    server = salt.ext.six.moves.xmlrpc_client.ServerProxy(xml_rpc)

    return server, user, password


def _list_nodes(full=False):
    '''
    Helper function for the list_* query functions - Constructs the
    appropriate dictionaries to return from the API query.

    full
        If performing a full query, such as in list_nodes_full, change
        this parameter to ``True``.
    '''
    server, user, password = _get_xml_rpc()
    auth = ':'.join([user, password])

    vm_pool = server.one.vmpool.info(auth, -1, -1, -1, -1)[1]

    vms = {}
    for vm in etree.XML(vm_pool):
        name = vm.find('NAME').text
        vms[name] = {}

        cpu_size = vm.find('TEMPLATE').find('CPU').text
        memory_size = vm.find('TEMPLATE').find('MEMORY').text

        private_ips = []
        for nic in vm.find('TEMPLATE').findall('NIC'):
            private_ips.append(nic.find('IP').text)

        vms[name]['id'] = vm.find('ID').text
        vms[name]['image'] = vm.find('TEMPLATE').find('TEMPLATE_ID').text
        vms[name]['name'] = name
        vms[name]['size'] = {'cpu': cpu_size, 'memory': memory_size}
        vms[name]['state'] = vm.find('STATE').text
        vms[name]['private_ips'] = private_ips
        vms[name]['public_ips'] = []

        if full:
            vms[vm.find('NAME').text] = _xml_to_dict(vm)

    return vms


def _list_images(server=None, user=None, password=None):
    '''
    Lists all images available to the user and the user's groups.
    '''
    if not server or not user or not password:
        server, user, password = _get_xml_rpc()

    auth = ':'.join([user, password])
    image_pool = server.one.imagepool.info(auth, -1, -1, -1)[1]

    images = {}
    for image in etree.XML(image_pool):
        images[image.find('NAME').text] = _xml_to_dict(image)

    return images


def _list_security_groups(server=None, user=None, password=None):
    '''
    Lists all security groups available to the user and the user's groups.
    '''
    if not server or not user or not password:
        server, user, password = _get_xml_rpc()

    auth = ':'.join([user, password])
    secgroup_pool = server.one.secgrouppool.info(auth, -1, -1, -1)[1]

    groups = {}
    for group in etree.XML(secgroup_pool):
        groups[group.find('NAME').text] = _xml_to_dict(group)

    return groups


def _list_templates(server=None, user=None, password=None):
    '''
    Lists all templates available to the user and the user's groups.
    '''
    if not server or not user or not password:
        server, user, password = _get_xml_rpc()

    auth = ':'.join([user, password])
    template_pool = server.one.templatepool.info(auth, -1, -1, -1)[1]

    templates = {}
    for template in etree.XML(template_pool):
        templates[template.find('NAME').text] = _xml_to_dict(template)

    return templates


def _list_vms(server=None, user=None, password=None):
    '''
    Lists all virtual machines available to the user and the user's groups.
    '''
    if not server or not user or not password:
        server, user, password = _get_xml_rpc()

    auth = ':'.join([user, password])
    vm_pool = server.one.vmpool.info(auth, -1, -1, -1, 3)[1]

    vms = {}
    for v_machine in etree.XML(vm_pool):
        vms[v_machine.find('NAME').text] = _xml_to_dict(v_machine)

    return vms


def _list_vns(server=None, user=None, password=None):
    '''
    Lists all virtual networks available to the user and the user's groups.
    '''
    if not server or not user or not password:
        server, user, password = _get_xml_rpc()

    auth = ':'.join([user, password])
    vn_pool = server.one.vnpool.info(auth, -1, -1, -1)[1]

    vns = {}
    for v_network in etree.XML(vn_pool):
        vns[v_network.find('NAME').text] = _xml_to_dict(v_network)

    return vns


def _xml_to_dict(xml):
    '''
    Helper function to covert xml into a data dictionary.

    xml
        The xml data to convert.
    '''
    dicts = {}
    for item in xml:
        key = item.tag.lower()
        idx = 1
        while key in dicts:
            key += str(idx)
            idx += 1
        if item.text is None:
            dicts[key] = _xml_to_dict(item)
        else:
            dicts[key] = item.text

    return dicts
