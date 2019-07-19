#!/usr/bin/env python3
"""
A sample script to create cost report usage per instance type

"""

import argparse
import datetime
import operator
import prettytable
import time
import collections
import re

import matplotlib.pyplot as plt
from matplotlib import colors

from boto.ec2.instance import Instance
from boto.ec2.ec2object import TaggedEC2Object
import config
from boto.exception import EC2ResponseError

_CLOUD_DEV_MACHINE = 'cloud_dev_machine'

def strip(x): return x.replace('\n','').strip() if x else ''


InstanceMetadata = collections.namedtuple('InstanceMetadata', [
  'id', 'name', 'owner', 'state', 'private_dns', 'public_dns', 'stopped_time'
])


def object_sort_key(obj):
  """
  Key function for sorting collections of EC2 objects.
  :param obj: The object to create a sort key
  :return: A key suitable for sorting, based on the object's configuration
  """
  # TODO(ltd): Move to utils


  if not isinstance(obj, (Instance)):
    return None

  fields = [
    obj.tags.get(config.INSTANCE_ENVIRONMENT_KEY, 'unknown'),
    obj.tags.get(config.INSTANCE_PURPOSE_KEY, 'unknown'),
    obj.id
  ]

  if hasattr(obj, 'cidr_block'):
    fields.insert(2, obj.cidr_block if obj.cidr_block else 'unknown')

  if hasattr(obj, 'availability_zone'):
    fields.insert(2, obj.availability_zone if obj.availability_zone else 'unknown')

  return fields

def generate_role(obj):
  """
  Generates a roledef for an object based on its configured environment and purpose.
  :param obj: The object to generate a roledef
  :return: A roledef string or None if the object is not fully configured
  """
  if isinstance(obj, dict):
    tags = obj.get('Tags', {})
  elif isinstance(obj, TaggedEC2Object):
    tags = obj.tags
  else:
    return None

  if not all([t in tags for t in (config.INSTANCE_ENVIRONMENT_KEY, config.INSTANCE_PURPOSE_KEY)]):
    return None

  return '{environment}_{purpose}'.format(
    environment=tags[config.INSTANCE_ENVIRONMENT_KEY],
    purpose=tags[config.INSTANCE_PURPOSE_KEY].replace('-', '_')
  )

def generate_host(obj, prepend_user=False, use_ip=False, user=None):
  """
  Generates a hostname for an instance based on its configured environment, purpose, and admin user.

  How user works:

  Not prepend_user -> user == ''
  prepend + user provided -> user = provided@
  prepend + no user provided -> user = tags[config.INSTANCE_USER_KEY] + '@'
  prepend + no user provided + no user tag -> ''

  :param obj: The object to generate a hostname (currently only Instances are supported)
  :param prepend_user: Whether the admin user should be prepended to the hostname (i.e. user@domain)
  :param use_ip: Whether or not to use the private IP instead of a generated hostname
  :return: A hostname string or None if the object is not fully configured
  """

  # TODO(ltd): Move to utils

  host_user = user or ''
  tags = obj.get('Tags', [])
  tags = { i['Key'] : i['Value'] for i in tags }
  if prepend_user:
    if user is None and config.INSTANCE_OWNER_KEY in tags:
      user = tags.get(config.INSTANCE_OWNER_KEY, '')
    if user is not None:
      host_user = user + ':'

  environment = ''
  if config.INSTANCE_ENVIRONMENT_KEY in tags:
    environment = tags.get(config.INSTANCE_ENVIRONMENT_KEY, '') + '-'

  purpose = ''
  if config.INSTANCE_PURPOSE_KEY in tags:
    purpose = tags.get(config.INSTANCE_PURPOSE_KEY, '') + '-'

  ip = obj.get('PrivateIpAddress', None)
  identifier = obj['InstanceId'].split('-')[-1]

  if use_ip:
    return '{user}{ip}'.format(
      user=host_user,
      ip=ip
    )
  else:
    return '{user}{environment}{purpose}{identifier}.{subdomain}'.format(
      user=host_user,
      environment=environment,
      purpose=purpose,
      identifier=identifier,
      subdomain=config.MANAGED_SUBDOMAIN
    )

def create_instance_details_table(instances):
  """
  Create a PrettyTable of the most commonly useful instance details.

  :param instances: A list of instances to generate from
  :return: A PrettyTable object
  """
  # TODO(ltd): Move to utils
  table = prettytable.PrettyTable(['ID', 'Role', 'Hostname', 'State', 'Instance Type',
                                   'Launch date'], sortby='Role', reversesort=True,
                                  sort_key=operator.itemgetter(2, 6))

  table.align['ID'] = 'l'
  table.align['Role'] = 'l'
  table.align['Hostname'] = 'r'
  table.padding_width = 2

  for instance in instances:
    role = generate_role(instance)
    host = generate_host(instance)
    table.add_row([instance['InstanceId'], role if role else 'unknown', host if host else 'unknown',
                   instance['State']['Name'], instance['InstanceType'], instance['LaunchTime']])

  return table


def _get_instance_metadata(instances):
  """
  Retrieves various metadata for one or more instances.

  :param instances: A list of :py:class:`boto.ec2.instance.Instance` objects
  :param include_shutdown_time: Whether to retrieve instances' scheduled shutdown times
  :return: A list of :py:class:`uc.fab.roles.cloud_testing.InstanceMetadata` objects
  """
  metadata = {}
 
  # 'id', 'name', 'owner', 'state', 'private_dns', 'public_dns', 'stopped_time'
  for instance in instances:
    if instance['State']['Name'] in ('running', 'stopped'):
      tags = instance.get('Tags', [])
      tags = {i['Key'] : i['Value'] for i in tags}
      stop_time = ''
      if instance['StateTransitionReason'] and instance['State']['Name'] == 'stopped':
        if '(' in  instance['StateTransitionReason']:
          stop_time = re.findall('.*\((.*)\)', instance['StateTransitionReason'])[0]
      metadata[instance['InstanceId']] = InstanceMetadata(
        instance['InstanceId'],
        tags.get(_CLOUD_DEV_MACHINE, ''),
        tags.get(config.INSTANCE_OWNER_KEY, ''),
        instance['State']['Name'],
        generate_host(instance),
        instance['PublicDnsName'],
        stop_time
      )
    else:
      metadata[instance['InstanceId']] = InstanceMetadata(
        instance['InstanceId'], tags.get(_CLOUD_DEV_MACHINE),tags.get(config.INSTANCE_OWNER_KEY), instance['State']['Name'], '', '', ''
      )

  return metadata

def create_instance_detail_file(instances, fname):
  metadata = _get_instance_metadata(instances)
  f = open(fname,"w+")
  f.write('\t'.join(['ID', 'Role', 'Hostname','Environment', 'State', 'Instance Type', 'Launch date', 
    'Owner', 'Name', 'Stopped Time','Days since Stopped']))
  for instance in instances:
    role = generate_role(instance)
    host = generate_host(instance)
    _id = instance['InstanceId']
    env = instance['KeyName']
    stop_days = 0
    if metadata[_id].stopped_time:
      delta = datetime.datetime.utcnow() - datetime.datetime.strptime(metadata[_id].stopped_time, '%Y-%m-%d %H:%M:%S GMT')
      stop_days = delta.days
    row = [_id, role if role else 'unknown', host if host else 'unknown', env,
      metadata[_id].state, instance['InstanceType'], instance['LaunchTime'].strftime('%Y-%m-%d %H:%M:%S GMT')]
    row.extend([strip(metadata[_id].owner), strip(metadata[_id].name), metadata[_id].stopped_time, str(stop_days)])
    f.write('\n' + '\t'.join(row))
  f.close() 
